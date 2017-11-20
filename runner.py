from argparse import ArgumentParser, Action, SUPPRESS, RawDescriptionHelpFormatter
import os
import textwrap as tw
import itertools
import json
import hashlib

def generate_unique_id(d, N=10):
    """
    Return a unique hash string for the dictionary ``d``.

    Parameters
    ----------
    d : dict
        the dictionary of meta-data to use to make the hash
    N : int, optional
        return the first ``N`` characters from the hash string
    """
    s = json.dumps(d, sort_keys=True).encode()
    return hashlib.sha1(s).hexdigest()[:N]

def parametrize(params):
    """
    Execute a function for the product of the parameters in the
    ``params`` dict, using ``itertools``.

    Pararameters
    ------------
    params : dict
        the dictionary holding the param lists
    """
    keys = sorted(list(params.keys()))
    params = list(itertools.product(*[params[k] for k in keys]))
    def wrapped(func):
        def func_wrapper(*args, **kwargs):
            for p in params:
                kwargs.update(dict(zip(keys, p)))
                func(*args, **kwargs)

        return func_wrapper
    return wrapped

def InfoAction(runner):

    class _InfoAction(Action):
        """
        Action similar to ``help`` to print out
        the various registered commands for the ``BenchmarkRunner``.
        class
        """
        def __init__(self,
                     option_strings,
                     dest=SUPPRESS,
                     default=SUPPRESS,
                     help=None):
            super(_InfoAction, self).__init__(
                option_strings=option_strings,
                dest=dest,
                default=default,
                nargs=0,
                help=help)

        def __call__(self, parser, namespace, values, option_string=None):

            print("Registered commands\n" + "-"*19)
            for i, command in enumerate(runner.commands):
                tag = runner.tags[i]
                header = "%d:" %i
                if len(tag):
                    header = header + " " + ", ".join(["'%s' = %s" %(k,tag[k]) for k in tag])
                header += "\n"
                print(str(header))

            parser.exit()

    return _InfoAction

class BenchmarkRunner(object):
    """
    Class to run ``benchmark.py`` commands in a reproducible manner.

    Parameters
    ----------
    test_path : str
        the path of the test module in the nbodykit source code we
        are running, e.g., ``benchmarks/test_fftpower.py``
    result_dir : str
        the directory where we want to save the results, passed via
        ``--bench-dir``
    """
    def __init__(self, test_path, result_dir):
        self.test_path = test_path
        self.result_dir = result_dir

        # track commands and tags for each
        self.commands = []
        self.tags = []

    def add_commands(self, testnames, ncores, samples):
        """
        Register benchmarks for different configurations of
        test names and number of cores.

        Parameters
        ----------
        testnames : list of str
            a list of the test functions we want to run
        ncores : list of int
            a list of the number of cores we want to run
        samples : list of str
            the list of names of benchmarking samples that we want to run
        """
        params = {'testname':testnames, 'ncores':ncores}
        if len(samples): params['sample'] = samples

        @parametrize(params)
        def _add_commands(testname, ncores, sample=None):

            def command(testname, ncores, sample=None):
                # the name of the benchmark test to run
                bench_name = self.test_path + "::" + testname

                # the output directory
                if sample is not None:
                    bench_dir = os.path.join(self.result_dir, sample, str(ncores))
                else:
                    bench_dir = os.path.join(self.result_dir, str(ncores))

                # make the command
                args = (bench_name, bench_dir, ncores)
                cmd = "python ../benchmark.py {} --bench-dir {} -n {}".format(*args)
                if sample is not None:
                    cmd += " --sample " + sample
                return cmd

            # and register
            tag = {'testname':testname, 'ncores':ncores}
            if sample is not None: tag['sample'] = sample
            self.register(command, tag)

        # add the commands
        _add_commands()

    def register(self, command, tag):
        """
        Register a new command with the specified tag.

        Parameters
        ----------
        command : str
            the command to run
        tag : dict
            the dict of key/values that represents this command
        """
        self.commands.append(command)
        self.tags.append(tag)

    def execute(self):
        """
        Execute the ``BenchmarkRunner`` command.
        """
        # parse and get the command
        ns, unknown = self.parse_args()

        # setup the output directory
        self._store_config(unknown)

        # get the command, optionally evaluating it
        command = self.commands[ns.testno]
        if callable(command):
            command = command(**self.tags[ns.testno])

        # append unknown command-line args
        command += ' ' + ' '.join(unknown)

        # execute
        self._execute(command)

    def _store_config(self, args):
        """
        Internal function to store the configuration.

        Here, the configuration consists of:

        - host: the NERSC host name
        - python_version: the python version we use to execute the test
        - git_tag: the git tag we checkout before running the tests

        This configuration dict will be hashed to a unique string, and the
        results stored in that dictionary. The dict is saved to the
        file ``config.json`` in the top-level directory if it doesn't exist
        already.
        """
        from benchmark import NERSCBenchmark

        # parse additional command line options that are being passed to benchmark.py
        parser = NERSCBenchmark.get_parser()

        # this is a hack using dummy arguments here so we can parse
        # successfully (these are ignored)
        dummy = ['benchname', '--sample', 'boss_like', '--bench-dir', 'None', '-n', '1']
        args = parser.parse_args(dummy + args)

        # the config dict
        config = {}
        config['host'] = os.environ.get('NERSC_HOST', None)
        config['python_version'] = args.py
        config['git_tag'] = args.tag

        # get the hash string
        hashstr = generate_unique_id(config)

        # update the result directory
        self.result_dir = os.path.join(self.result_dir, hashstr)
        if not os.path.exists(self.result_dir):
            os.makedirs(self.result_dir)

        # dump config to JSON file, if it doesnt exist
        cfg_file = os.path.join(self.result_dir, 'config.json')
        if not os.path.exists(cfg_file):
            json.dump(config, open(cfg_file, 'w'))


    def _execute(self, command):
        """
        Internal function to execute the command.

        Parameters
        ----------
        command : str
            the command to execute
        """
        # print the command
        c = tw.dedent(command).strip()
        c = tw.fill(c, initial_indent=' '*4, subsequent_indent=' '*4, width=80)
        print("executing:\n%s" %c)

        # execute
        os.system(command)

    def parse_args(self):
        """
        Parse the command-line arguments.
        """
        desc = ("run the ``benchmarks.py`` script from a set of registered commands"
                "\n\nUnrecognized command line arguments specified here will be passed\n"
                "to ``benchmark.py``; see ``benchmark.py`` for options")
        parser = ArgumentParser(description=desc, formatter_class=RawDescriptionHelpFormatter)

        h = 'the integer number of the test to run'
        parser.add_argument('testno', type=int, help=h)

        h = 'print out the various commands'
        parser.add_argument('-i', '--info', action=InfoAction(self), help=h)

        ns, unknown = parser.parse_known_args()

        # make sure the integer value is valid
        if not (0 <= ns.testno < len(self.commands)):
            N = len(self.commands)
            raise ValueError("input ``testno`` must be between [0, %d]" %N)

        return ns, unknown