everdb-python
=============

*everdb-python* is the Python language implementation of [everdb](https://github.com/Knio/everdb).

[![Build Status][buildlogo-python]](https://travis-ci.org/Knio/everdb-python)
[![Coverage Status][coveragelogo-python]](https://coveralls.io/r/Knio/everdb-python)

[buildlogo-python]: https://travis-ci.org/Knio/everdb-python.svg?branch=master
[coveragelogo-python]: https://img.shields.io/coveralls/Knio/everdb-python.svg?branch=master



TODO
----

 - [ ] Save format in Array header
 - [x] Benchmarks for Blob, Array, Hash
 - [ ] Benchmark page comparing sqlite, bsd, etc
 - [x] Caching to speed up benchmarks
 - [ ] Store explicit db data structures in hash values (`h[x] = Blob()`)
    - [ ] DB root hash to access structures
 - [ ] Store implicit large data in hash values (`h[x] = 'xxx'*(2**32)`)
 - [ ] File header with db state and version
 - [ ] Fixed-length struct array datatype
