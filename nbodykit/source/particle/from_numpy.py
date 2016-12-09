from nbodykit.io.stack import FileStack
from nbodykit.base.particles import ParticleSource
from nbodykit.base.painter import Painter
from nbodykit import CurrentMPIComm
import numpy

class ParticlesFromNumpy(ParticleSource):
    """
    A source of particles from numpy array
    """
    @CurrentMPIComm.enable
    def __init__(self, data, comm=None, **kwargs):
        """
        Parameters
        ----------
        comm : MPI.Communicator
            the MPI communicator
        data : numpy.array
            a structured array holding the 
        
        """
        self.comm    = comm
        self._source = data
        if data.dtype.names is None:
            raise ValueError("input data should be a structured numpy array")
        
        # verify data types are the same
        dtypes = self.comm.gather(data.dtype, root=0)
        if self.comm.rank == 0:
            if any(dt != dtypes[0] for dt in dtypes):
                raise ValueError("mismatch between dtypes across ranks in ParticlesFromNumpy")
        self.dtype = data.dtype

        # update the meta-data
        self.attrs.update(kwargs)

        ParticleSource.__init__(self, comm)

    def __getitem__(self, col):
        """
        Return a column from the underlying file source
        
        Columns are returned as dask arrays
        """
        if col in self._source.dtype.names:
            import dask.array as da
            return da.from_array(self._source[col], chunks=100000)

        return ParticleSource.__getitem__(self, col)

    @property
    def size(self):
        return len(self._source)
        
    @property
    def hcolumns(self):
        """
        The union of the columns in the file and any transformed columns
        """
        return list(self._source.dtype.names)