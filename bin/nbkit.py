#! /usr/bin/env python

import argparse
import logging
import os
from mpi4py import MPI

from nbodykit.extensionpoints import Algorithm, algorithms
from nbodykit.extensionpoints import DataSource, Transfer, Painter
from nbodykit.plugins import ListPluginsAction, load

# configure the logging
rank = MPI.COMM_WORLD.rank
name = MPI.Get_processor_name()
logging.basicConfig(level=logging.DEBUG,
                    format='rank %d on %s: '%(rank,name) + \
                            '%(asctime)s %(name)-15s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M')


def config_stream(value):
    if os.path.exists(value):
        return open(value, 'r').read()
    else:
        return value
    
class HelpAction(argparse.Action):
    """
    Help action that replicates the behavior of subcommands, 
    i.e., `python prog.py subcommand -h` prints the
    help for the subcommand
    """
    def __init__(self,
                 option_strings,
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help=None):
        super(HelpAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        name = getattr(namespace, 'algorithm_name')
        if rank == 0:
            if name is not None:
                print(Algorithm.format_help(name))
            else:
                parser.print_help()
        parser.exit()
        
def main():
    
    valid_algorithms = list(vars(algorithms).keys())

    # initialize the main parser
    desc = "Invoke an `nbodykit` algorithm with the given parameters. \n\n"
    desc += "MPI usage: mpirun -n [n] python nbkit.py ... \n\n"
    desc += "Because MPI standard requires the python interpreter in mpirun commandline. \n"
    kwargs = {}
    kwargs['description'] = desc
    kwargs['fromfile_prefix_chars'] = '@'
    kwargs['formatter_class'] = argparse.ArgumentDefaultsHelpFormatter
    parser = argparse.ArgumentParser("nbkit.py", add_help=False, **kwargs)

    # add the arguments to the parser
    parser.add_argument('-o', '--output', help='the string specifying the output')
    parser.add_argument('algorithm_name', choices=valid_algorithms)
    parser.add_argument('-h', '--help', action=HelpAction, help='Help on an algorithm')
    parser.add_argument("-X", type=load, action="append", help="Add a directory or file for looking up plugins.")
    parser.add_argument('-c', '--config', type=config_stream, required=True,
                        help='the name of the file to read parameters from, using YAML syntax')
    
    # help arguments
    parser.add_argument('--list-datasources', nargs='*', action=ListPluginsAction(DataSource), help='List DataSource')
    parser.add_argument('--list-algorithms',  nargs='*', action=ListPluginsAction(Algorithm), help='List Algorithms')
    parser.add_argument('--list-painters',  nargs='*', action=ListPluginsAction(Painter), help='List Painters')
    parser.add_argument('--list-transfers',  nargs='*', action=ListPluginsAction(Transfer), help='List Transfer Functions')

    # configure printing
    parser.usage = parser.format_usage()[6:-1] + " ... \n"
    if MPI.COMM_WORLD.rank != 0:
        parser._print_message = lambda x, file=None: None

    # parse the command-line
    ns, args = parser.parse_known_args()
    alg_name = ns.algorithm_name; output = ns.output

    # configuration file passed via -c
    params, extra = Algorithm.parse_known_yaml(alg_name, ns.config)
    output = getattr(extra, 'output', None)
    
    # output is required
    if output is None:
        raise ValueError("argument -o/--output is required")
            
    # initialize the algorithm and run
    alg_class = getattr(algorithms, alg_name)
    alg = alg_class(**vars(params))

    # run and save
    result = alg.run()
    alg.save(output, result) 
       
if __name__ == '__main__':
    main()
