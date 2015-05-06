#!/usr/bin/env python
from __future__ import print_function, division

import sys, os, stat, io, struct
import gzip, tarfile

def is_stream_stat (st):
  """Check whether a stat struct is a FIFO or character device"""
  m = st.st_mode
  return stat.S_ISFIFO (m) or stat.S_ISCHR (m)

def slurp (path):
  with open (path, "rb") as f:
    return f.read ()

def gzip_size (f, reset = True):
  """Compute the uncompressed size of a gzip file.

  Result will be wrong if the size does not fit in a U32.
  Arguments:
  f -- a GzipFile.fileobj
  reset --- whether to reset the stream to its initial position
  """
  oldp = f.tell () if reset else None
  f.seek (-4, os.SEEK_END)
  n = struct.unpack ('I', f.read (4)) [0]
  if reset: f.seek (oldp, os.SEEK_SET)
  return n

class ConcatFileobjReader (io.RawIOBase):
  """Sequentially read a list of fileobjs"""
  def __init__ (self, fs):
    self.fileobjs = fs
  def readable (self): return True
  def readinto (self, b):
    sz = len (b)
    if len (self.fileobjs) == 0:
      return 0
    else:
      sz = self.fileobjs [0].readinto (b)
      if sz < len (b):
        self.fileobjs.pop (0).close ()
      if sz > 0: return sz
      else:  # try with next
        return self.readinto (b)
  def read (self, sz):
    b = bytearray (sz)
    nread = self.readinto (b)
    if nread == len (b): return b
    else:
      return b [:nread]
  def close (self):
    if not self.closed:
      for f in self.fileobjs: f.close ()
      self.closed = True

def cmdline (args):
  def setup_argparser ():
    """Only used for help -- the actual parsing is done manually"""
    import argparse
    _ = argparse.ArgumentParser (description = "Concatenates groups of regular and compressed files; outputs the resulting entries to stdout, packed under arbitrary names in a tar stream", epilog = "The tar output stream will contain one entry per -o option. Each -o causes all previously unsaved -i and -z inputs to be concatenated into an output entry with the specified name. This entry inherits its permission + ownership from its last  input. Streams (the size of which can only be determined by reading until encountering EOF) will be buffered into memory.")
    _.add_argument ("-i", "--input")
    _.add_argument ("-z", "--input-zip")
    _.add_argument ("-o", "--output-entry")
    return _
  argp = setup_argparser ()
  if len (args) < 1 or args [0] in { "-h", "--help" }:
    argp.print_help ()

  tarf = tarfile.open (fileobj = sys.stdout, mode="w|")

  cat_files = []  # fileobjs to be concatenated
  tsize = 0  # total file size
  lastin = None  # last path in concatenation
  
  def add_str (buf):
    cat_files.append (io.BytesIO (buf))
    return len (buf)
    
  while len (args) > 0:
    if len (args) < 2:
      argp.print_usage ()
    flag = args.pop (0); path = args.pop (0)
    if flag == "-i":
      lastin = path
      st = os.stat (path)
      if is_stream_stat (st):
        tsize += add_str (slurp (path))
      else:
        tsize += st.st_size
        cat_files.append (io.open (path, "rb"))
    elif flag == "-z":
      lastin = path
      st = os.stat (path)
      if is_stream_stat (st):
        # GzipFile doesn't do streams, tries to seek()
        with gzip.GzipFile (fileobj = io.BytesIO (slurp (path))) as gzipf:
          tsize += add_str (gzipf.read ())
      else:
        gzipf = gzip.open (path)
        tsize += gzip_size (gzipf.fileobj)
        cat_files.append (gzipf)
    elif flag == "-o":
      tinfo = tarf.gettarinfo (lastin, arcname = path)
      tinfo.type = tarfile.REGTYPE
      tinfo.size = tsize
      tarf.addfile (tinfo, fileobj = io.BufferedReader (ConcatFileobjReader (cat_files)))
      tsize = 0
      while len (cat_files) > 0:  # for 0-byte entries files might not be consummed
        cat_files.pop (0).close ()
    
  
if __name__ == "__main__":
  cmdline (sys.argv [1:])
