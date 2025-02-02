# Copyright 2011 Hugo Larochelle. All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without modification, are
# permitted provided that the following conditions are met:
# 
#    1. Redistributions of source code must retain the above copyright notice, this list of
#       conditions and the following disclaimer.
# 
#    2. Redistributions in binary form must reproduce the above copyright notice, this list
#       of conditions and the following disclaimer in the documentation and/or other materials
#       provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY Hugo Larochelle ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL Hugo Larochelle OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and documentation are those of the
# authors and should not be interpreted as representing official policies, either expressed
# or implied, of Hugo Larochelle.

import cPickle,os
import numpy as np
import scipy.io
from gzip import GzipFile as gfile

# This module includes useful functions for loading and saving datasets or objects in general

# Functions to load datasets in different formats.
# Those functions output a pair (data,metadata), where 
# metadata is a dictionary.

### Some helper classes ###

class IteratorWithFields():
    """
    An iterator over the rows of a Numpy array, which separates each row into fields (segments)

    This class helps avoiding the creation of a list of arrays.
    The fields are defined by a list of pairs (beg,end), such that 
    data[:,beg:end] is a field.
    """

    def __init__(self,data,fields):
        self.data = data
        self.fields = fields

    def __iter__(self):
        for r in self.data:
            yield [r[beg:end] for (beg,end) in self.fields ]


class MemoryDataset():
    """
    An iterator over some data, but that puts the content 
    of the data in memory in Numpy arrays.

    Option 'field_shapes' is a list of tuples, corresponding
    to the shape of each fields.

    Option dtypes determines the type of each field (float,int,etc.).

    Optionally, the length of the dataset can also be
    provided. If not, it will be figured out automatically.
    """

    def __init__(self,data,field_shapes,dtypes,length=None):
        self.data = data
        self.field_shapes = field_shapes
        self.n_fields = len(field_shapes)
        self.mem_data = []
        if length == None:
            # Figure out length
            length = 0
            for example in data:
                length += 1
        self.length = length
        for i in range(self.n_fields):
            sh = field_shapes[i]
            if sh == (1,):
                mem_shape = (length,) # Special case of non-array fields. This will 
                                      # ensure that a non-array field is yielded
            else:
                mem_shape = (length,)+sh
            self.mem_data += [np.zeros(mem_shape,dtype=dtypes[i])]

        # Put data in memory
        t = 0
        if self.n_fields == 1:
            for example in data:
                self.mem_data[0][t] = example
                t+=1
        else:
            for example in data:
                for i in range(self.n_fields):
                    self.mem_data[i][t] = example[i]
                t+=1

    def __iter__(self):
        if self.n_fields == 1:
            for example in self.mem_data[0]:
                yield example
        else:
            for t in range(self.length):
                yield [ m[t] for m in self.mem_data ]


class FileDataset():
    """
    An iterator over a dataset file, which converts each
    line of the file into an example.

    The option 'load_line' is a function which, given 
    a string (a line in the file) outputs an example.
    """

    def __init__(self,filename,load_line):
        self.filename = filename
        self.load_line = load_line

    def __iter__(self):
        stream = open(os.path.expanduser(self.filename))
        for line in stream:
            yield self.load_line(line)
        stream.close()


### ASCII format ###

def ascii_load(filename, convert_input=float, last_column_is_target = False, convert_target=float):
    """
    Reads an ascii file and returns its data and metadata.

    Data can either be a simple numpy array (matrix), or an iterator over (numpy array,target)
    pairs if the last column of the ascii file is to be considered a target.

    Options 'convert_input' and 'convert_target' are functions which must convert
    an element of the ascii file from the string format to the desired format (default: float).

    Defined metadata: 
    - 'input_size'

    """

    f = open(os.path.expanduser(filename))
    lines = f.readlines()

    if last_column_is_target == 0:
        data = np.array([ [ convert_input(i) for i in line.split() ] for line in lines])
        return (data,{'input_size':data.shape[1]})
    else:
        data = np.array([ [ convert_input(i) for i in line.split()[:-1] ] + [convert_target(line.split()[-1])] for line in lines])
        return (IteratorWithFields(data,[(0,data.shape[1]-1),(data.shape[1]-1,data.shape[1])]),
                {'input_size':data.shape[1]-1})
    f.close()

### LIBSVM format ###

def libsvm_load_line(line,convert_non_digit_features=float,convert_target=str,sparse=True,input_size=-1):
    """
    Converts a line (string) of a libsvm file into an example (list).

    This function is used by libsvm_load().
    If sparse is False, option 'input_size' is used to determine the size 
    of the returned 1D array  (it must be big enough to fit all features).
    """
    line = line.strip()
    tokens = line.split()

    # Remove indices < 1
    n_removed = 0
    n_feat = 0
    for token,i in zip(tokens, range(len(tokens))):
        if token.find(':') >= 0:
            if token[:token.find(':')].isdigit():
                if int(token[:token.find(':')]) < 1: # Removing feature ids < 1
                    del tokens[i-n_removed]
                    n_removed += 1
                else:
                    n_feat += 1
        
    if sparse:
        inputs = np.zeros((n_feat))
        indices = np.zeros((n_feat),dtype='int')
    else:
        input = np.zeros((input_size))
    extra = []

    i = 0
    for token in tokens[1:]:
        id_str,input_str = token.split(':')
        if id_str.isdigit():
            if sparse:
                indices[i] = int(id_str)
                inputs[i] = float(input_str)
            else:
                input[int(id_str)-1] = float(input_str)
            i += 1
        else:
            extra += [convert_non_digit_features(id_str,input_str)]
            
    if sparse:
        example = [(inputs, indices), convert_target(tokens[0])]
    else:
        example = [input,convert_target(tokens[0])]
    if extra:
        example += extra
    return example

def libsvm_load(filename,convert_non_digit_features=float,convert_target=str,sparse=True,input_size=None):
    """
    Reads a LIBSVM file and returns the list of all examples (data) and metadata information.

    In general, each example in the list is a two items list [input, target] where
    - if sparse is True, input is a pair (values, indices) of two vectors 
      (vector of values and of indices). Indices start at 1;
    - if sparse is False, input is a 1D array such that its elements
      at the positions given by indices-1 are set to the associated values, and the
      other elemnents are 0;
    - target is a string corresponding to the target to predict.

    If a 'feature:value' pair is such that 'feature' is not an integer, 
    'value' will be converted to the desired format using option
    'convert_non_digit_features'. This option must be a callable function
    taking 2 string arguments, and will be called as follows:
         output = convert_non_digit_features(feature_str,value_str)
    where 'feature_str' and 'value_str' are 'feature' and 'value' in string format.
    Its output will be appended to the list of the given example.

    The input_size can be given by the user. Otherwise, will try to figure
    it out from the file (won't work if the file format is sparse and some of the
    last features are all 0!).

    Defined metadata: 
    - 'targets'
    - 'input_size'

    """

    stream = open(os.path.expanduser(filename))
    data = []
    metadata = {}
    targets = set()
    if input_size is None:
        given_input_size = None
        input_size = 0
    else:
        given_input_size = input_size

    for line in stream:
        example = libsvm_load_line(line,convert_non_digit_features,convert_target,True)
        max_non_zero_feature = max(example[0][1])
        if (given_input_size is None) and (max_non_zero_feature > input_size):
            input_size = max_non_zero_feature
        targets.add(example[1])
        # If not sparse, first pass through libsvm file just 
        # figures out the input_size and targets
        if sparse:
            data += [example]
    stream.close()

    if not sparse:
        # Now that we know the input_size, we can load the data
        stream = open(os.path.expanduser(filename))
        for line in stream:
            example = libsvm_load_line(line,convert_non_digit_features,convert_target,False,input_size)
            data += [example]
        stream.close()
        
    metadata['targets'] = targets
    metadata['input_size'] = input_size
    return data, metadata

### Generic save/load functions, using cPickle ###

def save(p, filename):
    f=file(filename,'wb')
    cPickle.dump(p,f,cPickle.HIGHEST_PROTOCOL) 
    f.close()

def load(filename): 
    f=file(filename,'rb')
    y=cPickle.load(f)
    f.close()
    return y

def gsave(p, filename):
    f=gfile(filename,'wb')
    cPickle.dump(p,f,cPickle.HIGHEST_PROTOCOL) 
    f.close()

def gload(filename):
    f=gfile(filename,'rb')
    y=cPickle.load(f)
    f.close()
    return y


### For loading large datasets which don't fit in memory ###

def load_line_default(line):
    return np.array([float(i) for i in line.split()]) # Converts each element to a float

def load_from_file(filename,load_line=load_line_default):
    """
    Loads a dataset from a file, without loading it in memory.
    """
    return FileDataset(filename,load_line)
    
