#!/usr/bin/env python

# -*- coding: iso8859-1 -*-
#
# $Id: version.py 133 2006-03-24 10:30:20Z fuller $
#
# check_smartmon
# Copyright (C) 2006  daemogorgon.net
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License along
#   with this program; if not, write to the Free Software Foundation, Inc.,
#   51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os.path
import sys

from optparse import OptionParser

# Package versioning
__author__ = "fuller <fuller@daemogorgon.net>"
__version__ = "$Revision$"


# path to smartctl
SMARTCTL_PATH = "/usr/sbin/smartctl"

# application wide verbosity (can be adjusted with -v [0-3])
VERBOSITY = 0

NAGIOS_OK = 0
NAGIOS_WARNING = 1
NAGIOS_CRITICAL = 2

class DeviceThreshold(object):
    """DeviceThreshold contains status limits.  
    It is logically paired to DriveInfo"""
    warningTemperature = 55
    criticalTemperature = 60
    criticalReallocatedSectors = 0 # failures are bad
    warningSpinRetryCount = 0 # I don't know a reasonable default
    criticalSpinRetryCount = 0 # I don't know a reasonable default
    warningReadFailureSectors = 0 # I don't know a reasonable default
    criticalReadFailureSectors = 0 # I don't know a reasonable default

class NagiosInfo(object):
    status = NAGIOS_OK
    message = ""

class DeviceInfo(object):
    """DeviceInfo contains SMART data about a drive"""
    device = "" # name of the device
    # initialize to failure status
    temperature = 1000
    reallocatedSectors = 1000 # sectors are reallocated when writes fail
    spinRetryCount = 1000
    readFailureSectors = 1000 # sectors where data couldn't be read.  Sometimes, subsequent reads are successful.  This is still bad
    def __init__(self, device):
        self.device = device

    def parseSmartCtlOutput(self, output):
        lines = output.split("\n")
        for line in lines:
            parts = line.split()
            if len(parts):
                # 194 is the temperature value id
                if parts[0] == "194":
                    self.temperature = int(parts[9])
                # 5 is reallocated sectors
                elif parts[0] == "5":
                    self.reallocatedSectors = int(parts[9])
                # 10 is spin retry
                elif parts[0] == "10":
                    self.spinRetryCount = int(parts[9])
                # 197 is read failures
                elif parts[0] == "197":
                    self.readFailureSectors = int(parts[9])
 
    def getNagiosInfo(self, driveThreshold):
        nagiosInfo = NagiosInfo()

        nagiosInfo.message += self.device + "("
        compareSimpleStat(self.temperature, driveThreshold.warningTemperature, driveThreshold.criticalTemperature, "temperature", nagiosInfo)
        nagiosInfo.message += ", "
        compareSimpleStat(self.reallocatedSectors, driveThreshold.criticalReallocatedSectors, driveThreshold.criticalReallocatedSectors, "write-failures", nagiosInfo)
        nagiosInfo.message += ", "
        compareSimpleStat(self.spinRetryCount, driveThreshold.warningSpinRetryCount, driveThreshold.criticalSpinRetryCount, "spin-retry", nagiosInfo)
        nagiosInfo.message += ", "
        compareSimpleStat(self.readFailureSectors, driveThreshold.warningReadFailureSectors, driveThreshold.criticalReadFailureSectors, "read-failures", nagiosInfo)
        nagiosInfo.message += ")"

        return nagiosInfo


def compareSimpleStat(stat, warningLevel, criticalLevel, statName, nagiosInfo):
    if stat > criticalLevel:
        nagiosInfo.status = max(nagiosInfo.status, NAGIOS_CRITICAL)
        nagiosInfo.message += "CRITICAL-" + statName.upper() + ":"
    elif stat > warningLevel:
        nagiosInfo.status = max(nagiosInfo.status, NAGIOS_CRITICAL)
        nagiosInfo.message += "WARNING-" + statName.upper() + ":"
    else:
        nagiosInfo.message += statName + ":"
    nagiosInfo.message += str(stat)
    nagiosInfo.message += " of (" + str(warningLevel) + "," + str(criticalLevel) + ")"



def parseCmdLine(args):
    """
    Commandline parsing.
    """

    usage = "usage: %prog [options] device"
    version = "%%prog %s" % __version__

    parser = OptionParser(usage=usage, version=version)
    parser.add_option("-d", "--device", action="store", dest="device",
                      default=None, metavar="DEVICE",
                      help="device to check")
    parser.add_option("-v", "--verbosity", action="store", dest="verbosity",
                      type="int", default=0, metavar="LEVEL",
                      help="set verbosity level to LEVEL;"
                           " defaults to 0 (quiet),possible values go up to 3")
    parser.add_option("-w", "--warning-threshold", action="store",
                      dest="warningThreshold", metavar="TEMP", type="int",
                      default=55,
                      help="set temperature warning threshold to "
                           "given temperature (defaults to 55)")
    parser.add_option("-c", "--critical-threshold", metavar="TEMP",
                      action="store", type="int", dest="criticalThreshold",
                      default="60",
                      help="set temperature critical threshold to "
                           "given temperature (defaults to 60)")

    return parser.parse_args(args)


def checkDevice(device):
    """
    Check if device exists and permissions are ok.
    Returns:
        - 0 ok
        - 1 no such device
        - 2 no read permission given
    """
    
    vprint(3, "Check if %s does exist and can be read" % device)
    if not os.access(device, os.F_OK):
        return 1, "UNKNOWN: no such device found \"" + device + "\""
    elif not os.access(device, os.R_OK):
        return 2, "UNKNOWN: no read permission given"
    else:
        return 0, ""


def checkSmartMonTools(path):
    """
    Check if smartctl is available and can be executed.
    Returns:
        - 0 ok
        - 1 no such file
        - 2 cannot execute file
    """

    vprint(3, "Check if %s does exist and can be read" % path)
    if not os.access(path, os.F_OK):
        return 1, "UNKNOWN: cannot find %s" % path
    elif not os.access(path, os.X_OK):
        return 2, "UNKNOWN: cannot execute %s" % path
    else:
        return 0, ""

def getDevices(path):
    cmd = "%s --scan" % (path)
    (child_stdin, child_stdout, child_stderr) = os.popen3(cmd)
    line = child_stderr.readline()
    if len(line):
        return 3, "UNKNOWN: call exits unexpectedly (%s)" % line, "", ""

    devices = []
    for line in child_stdout:
        parts = line.split()
        devices.append(parts[0])

    return devices

def callSmartMonTools(path, device):
    # get health status
    cmd = "%s -H %s" % (path, device)
    vprint(3, "Get device health status: %s" % cmd)
    (child_stdin, child_stdout, child_stderr) = os.popen3(cmd)
    line = child_stderr.readline()
    if len(line):
        return 3, "UNKNOWN: call exits unexpectedly (%s)" % line, "", ""
    healthStatusOutput = ""
    for line in child_stdout:
        healthStatusOutput += line

    # get temperature
    cmd = "%s -A %s" % (path, device)
    vprint(3, "Read device SMART attributes: %s" % cmd)
    (child_stdin, child_stdout, child_stderr) = os.popen3(cmd)
    line = child_stderr.readline()
    if len(line):
        return 3, "UNKNOWN: call exits unexpectedly (%s)" % line, "", ""

    smartAttributeOutput = ""
    for line in child_stdout:
        smartAttributeOutput += line

    return 0 ,"", healthStatusOutput, smartAttributeOutput


def parseOutput(healthMessage):
    """
    Parse smartctl output
    Returns (health status).
    """

    # parse health status
    #
    # look for line '=== START OF READ SMART DATA SECTION ==='
    statusLine = ""
    lines = healthMessage.split("\n")
    getNext = 0
    for line in lines:
        if getNext:
            statusLine = line
            break
        elif line == "=== START OF READ SMART DATA SECTION ===":
            getNext = 1
    parts = statusLine.split()
    healthStatus = parts[-1]
    vprint(3, "Health status: %s" % healthStatus)

    return (healthStatus)


def createReturnInfo(healthStatus, nagiosInfo):
    """
    Create return information according to given thresholds.
    """

    # this is absolutely critical!
    if healthStatus != "PASSED":
        return 2, "CRITICAL: device does not pass health status"

    return nagiosInfo.status, nagiosInfo.message

def exitWithMessage(value, message):
    """
    Exit with given value and status message.
    """

    print message
    sys.exit(value)


def vprint(level, message):
    """
    Verbosity print.

    Decide according to the given verbosity level if the message will be
    printed to stdout.
    """

    if level <= VERBOSITY:
        print message


if __name__ == "__main__":
    (options, args) = parseCmdLine(sys.argv)
    VERBOSITY = options.verbosity

    thresholds = DeviceThreshold()
    thresholds.warningTemperature = options.warningThreshold
    thresholds.criticalTemperature = options.criticalThreshold

    # check if we have smartctl available
    (value, message) = checkSmartMonTools(SMARTCTL_PATH)
    if value != 0:
        exitWithMessage(3, message)
    # fi
    vprint(1, "Path to smartctl: %s" % SMARTCTL_PATH)

    # either scan for all devices or set specified
    devices =[]
    if options.device is not None:
        devices.append(options.device)
    else:
        devices = getDevices(SMARTCTL_PATH)

    overallReturnValue = NAGIOS_OK
    overallReturnMessage =""

    for device in devices:
        # check if we can access 'path'
        vprint(2, "Check device")
        (value, message) = checkDevice(device)
        if value != 0:
            exitWithMessage(3, message)

        # call smartctl and parse output
        vprint(2, "Call smartctl")
        (value, message, healthStatusOutput, smartAttributeOutput) = callSmartMonTools(SMARTCTL_PATH, device)
        if value != 0:
            exitWithMessage(value, message)
        vprint(2, "Parse smartctl output")
        (healthStatus) = parseOutput(healthStatusOutput)

        deviceInfo = DeviceInfo(device)
        deviceInfo.parseSmartCtlOutput(smartAttributeOutput)
        nagiosInfo = deviceInfo.getNagiosInfo(thresholds)
        vprint(3, "SMART Output: %s" %nagiosInfo.message)

        vprint(2, "Generate return information")
        (currValue, currMessage) = createReturnInfo(healthStatus, nagiosInfo)
        vprint(1, "%d, %s" % (currValue, currMessage))
        overallReturnValue = max(overallReturnValue, currValue)
        overallReturnMessage += currMessage + "\n"

    # exit program
    exitWithMessage(overallReturnValue, overallReturnMessage)
