# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Source code based in parts on code from: https://github.com/UnravelTEC/Raspi-Driver-SCD30

# This module uses the services of the C pigpio library. pigpio must be running on the Pi(s) whose GPIO are to be manipulated.
# cmd ref: http://abyz.me.uk/rpi/pigpio/python.html#i2c_write_byte_data
#from typing_extensions import final
import pigpio  # aptitude install python-pigpio
import time
import struct
import sys
import math
import crcmod  # aptitude install python-crcmod
import os
import signal
from subprocess import call
import datetime
import logging
import argparse
from influxdb import InfluxDBClient

# global handle


parser = argparse.ArgumentParser()
parser.add_argument('--logdir', type=str, default='./logging',
                    help='path where to store logging')
parser.add_argument('--meas_interval', type=int, default=2, help='time interval between sensor readouts')
parser.add_argument('--sensorhost', type=str, default='127.0.0.1',
                    help='(IP) address of database')
parser.add_argument('--pressure', type=int, default=944, help="pressure at geolocation (mbar)")
parser.add_argument('--dbhost', type=str, default='localhost', help='(IP) address of database')
parser.add_argument('--dbport', type=int, default=8086, help='database port')
parser.add_argument('--dbuser', type=str, default="admin", help='database user')
parser.add_argument('--dbpassword', type=str, default="admin", help='database user password')
parser.add_argument('--dbname', type=str, default="mydb",
                    help='database name')
parser.add_argument(
    '-d', '--debug',
    help="Print lots of debugging statements",
    action="store_const", dest="loglevel", const=logging.DEBUG,
    default=logging.DEBUG,
)
parser.add_argument(
    '-v', '--verbose',
    help="Be verbose",
    action="store_const", dest="loglevel", const=logging.INFO,
)

class SCD30(object):
    """Class for controlling the scd-30 sensor"""

    def __init__(self, logger, PIGPIO_HOST='127.0.0.1', pressure_mbar=944, MEAS_INTERVAL=2):

        self.logger = logger

        # I2C specifics
        self.I2C_SLAVE = 0x61
        self.I2C_BUS = 1

        # PIGPIO specifics
        self.PIGPIO_HOST = PIGPIO_HOST


        # sensor specifics
        self.pressure_mbar = pressure_mbar
        self.MEAS_INTERVAL = MEAS_INTERVAL

        self.DEFAULT_ERROR_COUNT = 20
        self.fail_counter = self.DEFAULT_ERROR_COUNT


        # CRC checksum specifics
        self.f_crc8 = crcmod.mkCrcFun(0x131, 0xFF, False, 0x00)

        # catch closing of the program to avoid IC2 blocking
        signal.signal(signal.SIGINT, self.exit_hard)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

        # grep exits 0 if match found
        deviceOnI2C = call(
            "i2cdetect -y 1 0x61 0x61|grep '\--' -q", shell=True)


        if deviceOnI2C:
            self.logger.info("I2Cdetect found SCD30")
        else:
            self.logger.error("SCD30 (0x61) not found on I2C bus")
            raise


    def calcCRC(self, TwoBdataArray):
        return self.f_crc8(bytearray(TwoBdataArray))

    def calcFloat(self, sixBArray):
        struct_float = struct.pack('>BBBB', sixBArray[0], sixBArray[1], sixBArray[3], sixBArray[4])
        float_values = struct.unpack('>f', struct_float)
        first = float_values[0]
        return float(first)

    def connect(self):
        try:
            self.pi_handle = pigpio.pi(self.PIGPIO_HOST)


            if not self.pi_handle.connected:
                self.logger.error("Connection could not be established with pigpio daemon at " + self.PIGPIO_HOST )
                raise IOError('PIGPIO daemon connection failed')
        except:
            self.logger.error("PIGPIO connection error")
            raise

        try:
            self.i2c_handle = self.pi_handle.i2c_open(self.I2C_BUS, self.I2C_SLAVE)
        except:
            self.logger.error("I2C opening of connection failed")
            raise


    def disconnect(self):
        try:
            self.pi_handle.i2c_close(self.i2c_handle)
        except:
            self.error("I2C closing of connection failed")
            raise

    def stop_measurement(self):
        ret = self.i2cWrite([0x01, 0x04])
        if ret == -1:
            self.logger.error("Sending stop measurement command unsuccessful")
        
    def start_measurement(self):
        LSB = 0xFF & self.pressure_mbar
        MSB = 0xFF & (self.pressure_mbar >> 8)
        ret = self.i2cWrite([0x00, 0x10, MSB, LSB, self.calcCRC([MSB,LSB])])
        if ret == -1:
            self.logger.error("Starting measurements unsuccessful")
            self.disconnect()

        self.logger.info('Starting measuring with ' + str(self.pressure_mbar) + 'mbar')

    def i2cWrite(self, data):
        try:
            self.pi_handle.i2c_write_device(self.i2c_handle, data)
        except:
            self.logger.debug("Writing to I2C failed")
            return -1

        return True

    def read_n_bytes(self, n):
        try:
            (count, data) = self.pi_handle.i2c_read_device(self.i2c_handle, n)
        except:
            self.logger.error("Failed reading from I2C")
            raise

        if count == n:
            self.logger.debug("read_n_bytes(" + str(n) + ") successful")
            if n % 3 == 0:
                self.logger.debug("Multiple of 3 bytes read, calc checksum")
                for i in range(int(n / 3)):
                    offset = i * 3
                    sent_crc = data[offset + 2]
                    calc_crc = self.calcCRC([data[offset + 0], data[offset + 1]])
                    if sent_crc == calc_crc: # checksum correct
                        self.logger.debug(str(i) + ": crc " + hex(sent_crc) + " of " + hex(data[offset + 0]) + hex(data[offset + 1]) + " OK")
                    else: # checksum failure
                        self.logger.error(str(i) + ": crc " + hex(sent_crc) + " of " + hex(data[offset + 0]) + hex(data[offset + 1]) + " NOK, should be " + hex(calc_crc))
                        return False
                return data
        else:
            self.logger.error("Read bytes didn't return " + str(n) + " B, but " + str(count) + " B")
            return False

    def read_firmware_version(self):
        if self.i2cWrite([0xD1, 0x00]):
            firmware_version = self.read_n_bytes(3)
            if firmware_version:
                self.logger.info("Firmware version: " + hex(firmware_version[0]) + hex(firmware_version[1]))
                return True

        self.logger.error("Firmware version could not be read")

        return False

    def read_meas_interval(self):
    
        if self.i2cWrite([0x46, 0x00]) == -1:
            self.logger.error("Reading of measurement interval unsuccessful")
            return -1

        ret = self.read_n_bytes(3)
        if ret:
            interval = ret[0] * 256 + ret[1]
            self.logger.info("Current measurement interval: " + str(interval))
            return interval

        self.logger.error("Read measurement interval didnt return 3B")
        return -1

    def set_meas_interval(self, meas_interval):
    
        
        if self.i2cWrite([0x46, 0x00, 0x00, meas_interval,
                          self.calcCRC([0x00, meas_interval])]) == -1:
            self.logger.error("Writing of measurement interval unsuccessful")
            self.exit_hard()
            return -1

        ret = self.read_meas_interval()
        if ret == -1:
            self.logger.error("Measurement interval update unsuccessful")
            self.exit_hard()
        elif ret == meas_interval:
            self.logger.info("Measurement intervaled udpated successfully")
            return meas_interval
        else:
            return -1

    def read_asc_status(self):
        
        if self.i2cWrite([0x53, 0x06]) == -1:
            return -1

        data = self.read_n_bytes(3)

        if data == False:
            self.logger.warning("Read asc unsuccessful")
            return -1

        else:
            self.logger.debug("ASC read answer: " + hex(data[0]) + " " + hex(data[1]) + " " + hex(data[2]) + ".")

            if data[1] == 1:
                self.logger.info("ASC enabled")
                return 1
            elif data[1] == 0:
                self.logger.info("ASC disabled")
                return 0
            else:
                self.logger.info("ASC status unknown")
                return -1

    def exit_hard(self):
        self.reset()
        self.logger.info("Performed reset")
        
        self.pi_handle.i2c_close(self.i2c_handle)

    def exit_gracefully(self):
        self.stop_measurement()
        self.pi_handle.i2c_close(self.i2c_handle)
    
    def reset(self):

        ret = self.i2cWrite([0xD3, 0x04])
        if ret == -1:
            self.logger.warning("Reset unsuccesful")
            return
        time.sleep(0.5)

    def read_measurements(self):

        while True:
            if self.fail_counter == 0:
                self.logger.error("Unable to read data from sensor. Exiting")
                raise

            if self.i2cWrite([0x02, 0x02]) == -1:
                self.exit_hard()

            data = self.read_n_bytes(3)
            if data == False:
                self.fail_counter -= 1
                time.sleep(0.1)
                return False
            else:
                self.fail_counter = self.DEFAULT_ERROR_COUNT

            if data[1] == 1:
                tmp = 1
            else: 
                self.fail_counter -= 1
                time.sleep(0.1)

            #read measurement
            self.i2cWrite([0x03, 0x00])
            time.sleep(0.1)
            data = self.read_n_bytes(18)
            

            if data == False:
                self.logger.warning("read data unsuccessful")
                time.sleep(self.MEAS_INTERVAL)
                return False
            else:
                float_co2 = self.calcFloat(data[0:5])
                float_T = self.calcFloat(data[6:11])
                float_rH = self.calcFloat(data[12:17])

                return float_co2, float_T, float_rH

        return False

def main():

    FLAGS = parser.parse_args()
    #logging.basicConfig(filename='myapp.log', level=logging.INFO)

    logging.basicConfig(level=FLAGS.loglevel,
                        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename='info.log',
                        filemode='w')
    logger = logging.getLogger('RASPI_AIRDATA')
    #logger.setLevel(logging.DEBUG)
    # create logging directory if it does not exist
    if not os.path.exists(FLAGS.logdir):
        os.mkdir(FLAGS.logdir)

    # create file handler which logs even debug messages
    fh = logging.FileHandler(os.path.join(FLAGS.logdir,'info.log'))
    fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)


    try:
        # create database handler to store the sensor readings
        client = InfluxDBClient(FLAGS.dbhost, FLAGS.dbport,
                                FLAGS.dbuser, FLAGS.dbpassword, FLAGS.dbname)

        logger.info("Connected to InfluxDB")
   
    except:
        logger.error('Could not connect to database')
        exit(1)

    try:

        # create the handler for the SCD sensor
        scd30 = SCD30(logger=logger, PIGPIO_HOST=FLAGS.sensorhost,
                      pressure_mbar=FLAGS.pressure, MEAS_INTERVAL=FLAGS.meas_interval)

        scd30.connect()

        logger.info("Connected to SCD30")

    except:
        logger.error('Could not connect to SCD30')
        exit(1)

    try:

        meas_interval = scd30.read_meas_interval()

        if meas_interval != FLAGS.meas_interval:
            scd30.set_meas_interval(FLAGS.meas_interval)

        while True:
            measurements = scd30.read_measurements()

            if measurements != False:

                float_co2, float_T, float_rH = measurements

                # NaN sanity check
                if not( math.isnan(float_co2) or math.isnan(float_rH) or math.isnan(float_T) or float_co2 <= 0.0 or float_rH <= 0.0):

                    timestamp = datetime.datetime.utcnow().isoformat()
                    # create JSON structure of data
                    datapoints = [{
                        'measurement': 'air_quality',
                        'tags': {
                            'sensor': 'scd30'
                        },
                        'time':  timestamp,
                        'fields': {
                            'CO2_ppm': float_co2,
                            'temperature_degC': float_T,
                            'humidity_relPC': float_rH
                        },
                    }]

                    output_string = 'CO2_ppm: {0:.1f} | '.format(float_co2)
                    output_string += 'T: {0:.1f} °C | '.format( float_T )
                    output_string += 'rH: {0:.1f} %'.format( float_rH )

                    logger.info("Sensor read: "+output_string)

                    if not client.write_points(datapoints):
                       logger.debug("Writing data to database failed")

                else:
                    logger.debug("NaN sensor readouts")

            time.sleep(FLAGS.meas_interval-0.1)


    except KeyboardInterrupt:
        scd30.exit_gracefully()
        print('interrupted!')

if __name__ == '__main__':
    main()
