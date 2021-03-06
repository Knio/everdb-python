import os
import time
import random

import pytest

import everdb

TEST_NAME = 'test_archive.deleteme.dat'

def test_blob():
  assert everdb.Blob._header == [
    ('length', 'Q'),
    ('type', 'B'),
    ('num_blocks', 'I'),
  ]
  assert everdb.Blob._header_fmt == '!QBI'
  assert everdb.Blob._header_size == 17


def test_small_blob():
  db = everdb.Database(TEST_NAME, overwrite=True)
  db.freelist = []
  blob = db.blob()

  with pytest.raises(AttributeError):
    x = blob.foobar

  with pytest.raises(ValueError):
    x = blob.get_blocks(1, 0)

  with pytest.raises(ValueError):
    x = blob.get_blocks(0, 1)

  with pytest.raises(ValueError):
    x = blob.get_host_index(0)

  with pytest.raises(ValueError):
    x = blob.allocate(0)

  blob.resize(5)
  assert len(blob) == 5
  blob.write(0, b'AAAAA')

  blob.resize(10)
  assert len(blob) == 10
  blob.write(5, b'BBBBB')

  blob.resize(6)
  assert len(blob) == 6
  blob.write(2, b'C')

  r = blob.root

  db.close()
  assert os.path.getsize(TEST_NAME) == 12288

  #############

  db = everdb.Database(TEST_NAME)
  db.freelist = []
  blob = everdb.Blob(db, r)

  assert len(blob) == 6
  assert blob.read() == b'AACAAB'

  blob.resize(1024 * 1024 * 32)
  blob.resize(1024 * 1024 * 8)
  blob.resize(4096)

  with pytest.raises(IndexError):
    x = blob.get_host_index(1)

  blob.resize(0)
  assert blob.read() == b''

  db.close()
  os.remove(TEST_NAME)


def blob_tester(f):
  def wrapper():
    db = everdb.Database(TEST_NAME, overwrite=True)
    db.freelist = []
    blob = db.blob()
    r = blob.root

    # run the test
    # returns the expected conterts of the blob
    data = f(blob)

    db.close()
    db = everdb.Database(TEST_NAME)
    db.freelist = []
    blob = everdb.Blob(db, r)
    assert len(blob) == len(data)
    assert blob.read() == data
    blob.close()
    db.close()
    os.remove(TEST_NAME)
  return wrapper

@blob_tester
def test_new(blob):
  assert blob.length == 0
  assert blob.type == 1
  assert blob.num_blocks == 0
  assert bytes(blob.root_block) == (b'\0' * (4096 - 8 - 1 - 4 - 4)) + \
    b'\0\0\0\0\0\0\0\0' + \
    b'\1' + \
    b'\0\0\0\0' + \
    b'\x39\x2D\x5B\x5D'

  return b''

@blob_tester
def test_small_small(blob):
  blob.resize(5)
  blob.write(0, b'AAAAA')
  assert blob.read() == b'AAAAA'

  blob.resize(10)
  assert blob.read() == b'AAAAA\0\0\0\0\0'
  blob.write(5, b'BBBBB')
  assert blob.read() == b'AAAAABBBBB'

  blob.resize(6)
  blob.write(2, b'C')
  assert blob.read() == b'AACAAB'

  return b'AACAAB'


@blob_tester
def test_regular_1(blob):
  data = b'Hello World! ' * (1024 * 1024)
  blob.resize(len(data))
  blob.write(0, data)
  assert blob.read() == data
  return data

@blob_tester
def test_regular_2(blob):
  data = b'Hello World! ' * (1024 * 128)
  blob.resize(len(data))
  blob.write(0, data)
  blob.resize(8000)
  assert blob.read() == data[:8000]
  return data[:8000]

@blob_tester
def test_regular_3(blob):
  data = b'Hello World! ' * (1024)
  blob.resize(len(data))
  blob.write(0, data)
  blob.resize(12000)
  assert blob.read() == data[:12000]
  blob.resize(11000)
  assert blob.read() == data[:11000]
  return data[:11000]

@blob_tester
def test_regular_small(blob):
  data = b'Hello World! ' * (1024)
  blob.resize(len(data))
  blob.write(0, data)
  blob.resize(4000)
  assert blob.read() == data[:4000]
  assert blob.type == 1
  return data[:4000]


@blob_tester
def test_resize(blob):
  blob.resize(10000)
  blob.allocate(1)
  blob.allocate(512)
  blob.allocate(513)
  blob.allocate(512)
  blob.allocate(0)
  blob.resize(0)
  return b''

@blob_tester
def test_data_copy(blob):
  blob.resize(5)
  blob.write(0, b'Hello')
  blob.resize(10000)
  return b'Hello' + (b'\0' * 9995)


@blob_tester
def test_resize(blob):
  blob.resize(5)
  blob.write(0, b'Hello')
  # force it a 1 block
  blob.resize(4096 - blob._header_size + 1)
  assert blob.num_blocks == 1
  # test truncation
  blob.resize(4096)
  blob.write(5, b'\1' * 4091)
  assert blob.num_blocks == 1
  assert blob.read(0, 5) == b'Hello'

  # test truncation
  blob.resize(4095)
  assert bytes(blob.host[blob.get_host_index(0)][4090:4096]) == b'\1\1\1\1\1\0'

  return b'Hello' + (b'\1' * 4090)

if __name__ == '__main__':
  import cgitb
  cgitb.enable(format='text')
  test_data_copy()
