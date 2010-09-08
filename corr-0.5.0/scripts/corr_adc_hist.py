#!/usr/bin/env python

'''
Plots a histogram of the ADC values from a specified antenna and pol.\n

Revisions:
2010-08-05: JRM: Mods to support variable snap block length.
1.1 PVP Initial.\n

'''
import matplotlib
import time, corr, numpy, struct, sys, logging, pylab

# what format are the snap names and how many are there per antenna
snapName = 'adc_snap'
snapCount = 2
# what is the bram name inside the snap block
bramName = 'bram'

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n', lh.printMessages()
    print "Unexpected error:", sys.exc_info()
    try:
        c.disconnect_all()
    except:
        pass
    exit()

def exit_clean():
    try:
        c.disconnect_all()
    except:
        pass
    exit()

if __name__ == '__main__':
    from optparse import OptionParser
    p = OptionParser()
    p.set_usage('corr_adc_histogram.py [options] CONFIG FILE')
    p.add_option('-v', '--verbose', dest = 'verbose', action = 'store_true', help = 'Print raw output.')
    p.add_option('-a', '--antenna', dest = 'antAndPol', action = 'store', help = 'Specify an antenna and pol for which to get ADC histograms. 3x will give pol x for antenna three. 27y will give pol y for antenna 27. 3 on its own will give both \'x\' and \'y\' for antenna three. 3x,27y will do pol \'x\' of antenna 3 and pol \'y\' of antenna 27.')
    p.add_option('-c', '--compare', dest = 'comparePlots', action = 'store_true', help = 'Compare plots directly using the same y-axis for all plots.')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])
    if args==[]:
        print 'Please specify a configuration file!\nExiting.'
        exit()

# parse the antenna argument passed to the program
def parseAntenna(antArg):
    import re
    regExp = re.compile('^[0-9]{1,4}[xy]{0,2}$')
    ants = antArg.lower().replace(' ','').split(',')
    plotList = []
    for ant in ants:
        # is it valid?
        if not regExp.search(ant):
            print '\'' + ant + '\' is not a valid -a argument!\nExiting.'
            exit()
        antennaNumber = int(ant.replace('x', '').replace('y', ''))
        if (ant.find('x') < 0) and (ant.find('y') < 0):
            ant = ant + 'xy'
        if ant.find('x') > 0:
            plotList.append({'antenna':antennaNumber, 'pol':'x'})
        if ant.find('y') > 0:
            plotList.append({'antenna':antennaNumber, 'pol':'y'})
    return plotList

# the function that gets data given a required polarisation
def getUnpackedData(requiredPol):
    antLocation = c.get_ant_location(requiredPol['antenna'], requiredPol['pol'])
    # which fpga do we need?
    requiredFpga = antLocation[0]
    # which ADC is it on that FPGA?
    requiredFengInput = antLocation[4]
    # get the data
    packedData = c.ffpgas[requiredFpga].get_snap(snapName + str(requiredFengInput), [bramName])
    # unpack the data
    unpackedBytes = numpy.array(struct.unpack('>%ib'%(packedData['length']*4), packedData[bramName]))#/float(packedData['length']*4)
    return unpackedBytes, requiredFpga

# make the log handler
lh=corr.log_handlers.DebugLogHandler()

# check the specified antennae, if any
polList = []
if opts.antAndPol != None:
    polList = parseAntenna(opts.antAndPol)
else:
    print 'No antenna given for which to plot data.'
    exit_fail()

try:
    # make the correlator object
    print 'Connecting to correlator...',
    c=corr.corr_functions.Correlator(args[0], lh)
    for logger in c.floggers: logger.setLevel(10)
    print 'done.'

    # set up the figure with a subplot for each polarisation to be plotted
    fig = matplotlib.pyplot.figure()
    ax = fig.add_subplot(len(polList), 1, 1)

    # callback function to draw the data for all the required polarisations
    def drawDataCallback(comparePlots):
        counter = 1
        matplotlib.pyplot.clf()
        maxY = 0
        for pol in polList:
            matplotlib.pyplot.subplot(len(polList), 1, counter)
            unpackedData, ffpga = getUnpackedData(pol)
            histData = pylab.histogram(unpackedData, range(-128,129))[0]
            maxY = max(maxY, max(histData))
            matplotlib.pyplot.bar(range(-128,128), histData)
            if not comparePlots:
                matplotlib.pyplot.ylim(ymax = max(histData))
            matplotlib.pyplot.xticks(range(-130,131,10))
            matplotlib.pyplot.title('ant(' + str(pol['antenna']) + ') pol(' + pol['pol'] + ') ffpga(' + str(ffpga) + ') max(' + str(max(histData)) + ')')
            counter = counter + 1
        if comparePlots:
            counter = 1
            for pol in polList:
                matplotlib.pyplot.subplot(len(polList), 1, counter)
                matplotlib.pyplot.ylim(ymax = maxY)
                counter = counter + 1
        #fig.canvas.draw()
        fig.canvas.manager.window.after(100, drawDataCallback, comparePlots)

    # start the process
    fig.canvas.manager.window.after(100, drawDataCallback, opts.comparePlots)
    matplotlib.pyplot.show()
    print 'Plot started.'

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

print 'Done with all.'
exit_clean()

# end

