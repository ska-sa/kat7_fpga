#! /usr/bin/env python
"""Prints the output baseline order for this X engine design.
Author: Jason Manley
Revs:
2010-08-10  JRM Mods to use new corr package layout."""

import corr.sim,os,sys

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('corr_print_bl_order.py CONFIG_FILE')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

    config = corr.cn_conf.CorrConf(args[0])
    config_status = config.read_all()
    print '\n\nParsing config file %s...'%(args[0])
    sys.stdout.flush()
print 'Baseline ordering for %i antenna system (%i baselines):'%(config['n_ants'],config['n_bls'])

for t,bl in enumerate(corr.sim.get_bl_order(config['n_ants'])):
    print 't%i:'%t,bl

print "done"
