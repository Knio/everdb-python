import array
from collections import defaultdict
import weakref

import msgpack

from .page import Page, Field
from .page import BLOCK_SIZE, ZERO_BLOCK
from .page import SMALL_PAGE, REGULAR_PAGE
from .blob import Blob

'''
Linear hash table

hash table contains N (num_blocks) buckets,
with parameters L (level) and S (split).

2**L is the largest power of 2 not greater than N,
and 2**(L+1) is the next power of 2 that we are resizing the hash into

0 <= 2**L <= N < 2**(L+1)
0 <= S < 2**L
thus:
S <= 2*N

To resize the hash table, we split the bucket with index S into new locations
S and 2*S. We re-hash the items in bucket S with hash function H % (2**(L+1)),
and are guaranteed that the result will be <= N becase the origial hash function
result was S

Example:

Hash table of 4 buckets:

N=4
L=2
S=0

To grow the hash table by one bucket:
Allocate a new bucket, so N=5

split bucket S, and re-hash the items into buckets S and 2**L + S (= new bucket)
increment S by 1


'''

SUB_BUCKET_BITS = 8
SUB_BUCKET = (1 << SUB_BUCKET_BITS)
SUB_BUCKET_MASK = (SUB_BUCKET - 1)

def next_power_of_2(x):
  x -= 1
  x |= x >> 1
  x |= x >> 2
  x |= x >> 4
  x |= x >> 8
  x |= x >> 16
  return x + 1


class Bucket(Blob):

  def init_root(self):
    super(Bucket, self).init_root()
    self.resize(SUB_BUCKET << 2)
    self.get_header()[:] == [0] * SUB_BUCKET
    self.sync_header()

  def get_header(self):
    if self.num_blocks == 0:
      b = self.host[self.root]
    else:
      b = self.host[self.get_host_index(0)]
    return b.cast('H')[0:SUB_BUCKET << 1]\
      .cast('B').cast('H') # TODO python22668 workaround

  def get_sub(self, i):
    h = self.get_header()
    o, l = h[i << 1], h[(i << 1) + 1]
    if o == 0:
      return {}
    return msgpack.loads(self.read(o, l))

  def set_sub(self, i, bucket):
    if not bucket:
      data = b''
      d = 0
    else:
      data = msgpack.dumps(bucket)
      d = len(data)
    h = self.get_header()
    o, l = h[i << 1], h[(i << 1) + 1]
    if d <= l:
      h[(i << 1) + 1] = d
      if d == 0:
        h[i << 1] = 0
      else:
        self.write(o, data)
      self.sync_header()
      return
    # find and allocate new space for the sub bucket
    h[i << 1], h[(i << 1) + 1] = 0, 0
    intervals = sorted(zip(h[0::2], h[1::2]))
    d = next_power_of_2(d)
    o = SUB_BUCKET << 2
    for o0, l0 in intervals:
      if l0 == 0: continue
      if o + d <= o0: break
      o = o0 + next_power_of_2(l0)
    h[i << 1], h[(i << 1) + 1] = o, len(data)
    del h
    if o + d > self.length:
      n = self.num_blocks
      self.resize(o + d)

    h = self.get_header()
    # print(self.length)
    # if o >= 4064:
      # print(list(h))
      # print(self.read(0, SUB_BUCKET << 1))
    assert (h[i << 1], h[(i << 1) + 1]) == (o, len(data))

    self.write(o, data)
    # TODO don't do this
    self.sync_header()

  def items(self):
    b = {}
    h = self.get_header()
    for i in range(0, SUB_BUCKET << 1, 2):
      o, l = h[i], h[i + 1]
      if not l: continue
      b.update(msgpack.loads(self.read(o, l)))
    return b



PRIME = 1000000349

class Hash(Bucket):
  size  = Field('Q')
  split = Field('I')
  level = Field('B')

  def __init__(self, host, root, new):
    super(Hash, self).__init__(host, root, new)
    self.blob_cache = weakref.WeakValueDictionary()

  def init_root(self):
    self.size = 0
    self.split = 0
    self.level = 0
    super(Hash, self).init_root()

  def get_bucket(self, key):
    h = pow(2, hash(key), PRIME)
    b = h & ((SUB_BUCKET << 1 << self.level) - 1)
    if b >= ((1 << self.level) + self.split) << SUB_BUCKET_BITS:
      # bucket has no yet been split
      b = h & ((SUB_BUCKET << self.level) - 1)

    s = b & SUB_BUCKET_MASK
    b >>= SUB_BUCKET_BITS

    if self.level == 0 and self.split == 0:
      blob = self
    else:
      try:
        blob = self.blob_cache[b]
      except KeyError:
        blob = Bucket(self.host, self.get_host_index(b), False)
        self.blob_cache[b] = blob
        self.host.cache(blob)

    bucket = blob.get_sub(s)
    return s, blob, bucket

  def pack_value(self, val):
    return 0, val

  def unpack_value(self, val):
    t, v = val
    if t == 0:
      return v
    else:
      raise Exception('could not unpack value from hash table: %r' % val)

  def get(self, key):
    s, blob, bucket = self.get_bucket(key)
    val = bucket[key]
    return self.unpack_value(val)

  def set(self, key, value):
    s, blob, bucket = self.get_bucket(key)
    if key not in bucket:
      self.size += 1
      self.sync_header()

    bucket[key] = self.pack_value(value)
    blob.set_sub(s, bucket)
    if blob.length >= 3072:
      self.grow()


  def pop(self, key):
    s, blob, bucket = self.get_bucket(key)

    value = bucket.pop(key)
    blob.set_sub(s, bucket)

    self.size -= 1
    self.sync_header()

    # TODO shrink
    return self.unpack_value(value)

  def delete(self, key):
    self.pop(key)

  __getitem__ = get
  __setitem__ = set
  __delitem__ = delete

  def __contains__(self, key):
    s, blob, bucket = self.get_bucket(key)
    return key in bucket

  def __len__(self):
    return self.size

  def grow(self):
    s = self.split

    if s == 0 and self.level == 0:
      bucket = super(Hash, self).items()
      sl = slice(0, BLOCK_SIZE - self._header_size)
      self.host[self.root][sl] = ZERO_BLOCK[sl]
      self.type = REGULAR_PAGE
      self.allocate(2)
      b0 = Bucket(self.host, self.get_host_index(s), True)

    else:
      self.allocate(self.num_blocks + 1)
      b0 = Bucket(self.host, self.get_host_index(s), False)
      bucket = b0.items()
      if b0.type == REGULAR_PAGE:
        b0.allocate(0)
      b0.init_root()

    s0 = s
    s1 = s + (1 << self.level)

    b1 = Bucket(self.host, self.get_host_index(s1), True)

    # rehash bucket into b0 and b1
    bucket0 = defaultdict(dict)
    bucket1 = defaultdict(dict)

    for k, v in bucket.items():
      h = pow(2, hash(k), PRIME)
      b = h & ((SUB_BUCKET << 1 << self.level) - 1)
      u = b & SUB_BUCKET_MASK
      b >>= SUB_BUCKET_BITS

      if b == s0:
        bucket0[u][k] = v
      elif b == s1:
        bucket1[u][k] = v
      else:
        assert False, b

    for sub, d in bucket0.items():
      b0.set_sub(sub, d)

    for sub, d in bucket1.items():
      b1.set_sub(sub, d)

    # print('split into %d (%d) and %d (%d)' %
    #     (s0, s1, len(bucket0), len(bucket1)))

    if s + 1 == (1 << self.level):
      self.level += 1
      self.split = 0

    else:
      self.split += 1

    self.sync_header()

    for k, v in bucket.items():
      assert [0, self[k]] == v

