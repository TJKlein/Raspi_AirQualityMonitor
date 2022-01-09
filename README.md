# Raspberry Pi Indoor Air Quality Monitor

Objective of this repository is to provide code and instruction on how to turn your Raspberry Pi into an air measuring device.

## Hardware Requirements:
- [Raspberry Pi 4](https://www.raspberrypi.org/)
- [SCD30 Air Quality Sensor](https://www.sensirion.com/en/environmental-sensors/carbon-dioxide-sensors/carbon-dioxide-sensors-scd30/)
- [5" LCD Display](https://www.waveshare.com/product/displays/lcd-oled/lcd-oled-1/5inch-hdmi-lcd-b-with-bicolor-case.htm)

## Software Requirements

- [Python 3](https://www.python.org/downloads/)
- [crcmod](http://crcmod.sourceforge.net/)
- [pigpio](https://abyz.me.uk/rpi/pigpio/pigpiod.html)
- [InfluxDB](https://www.influxdata.com/)
- [Grafana](https://grafana.com/)



## Setup

### Database Setup
In order to store the measurement, we leverage a open source database for time series - [influxdb](https://www.influxdata.com/). Doing so allows for a quite easy to use way to handle the data and discard old data. Discarding old data is very important because time series data by can pile up pretty quickly and fill up your memory. To this end, influxdb offers what is called Retention policies. Leveraging an retention policy, essentially adds an expiration date to your data. Upon expiration the database will automatically take care of removing the data. In the following case, we create a database called "mydb" with a retention policy of 30 days. Consequentely, data that is older than 30 days, will be discarded.

#### Installation

More detailed instructions with different options can be found [here](https://docs.influxdata.com/influxdb/v1.8/introduction/install/).

First, we need to add the repositories to apt:

```
wget -qO- https://repos.influxdata.com/influxdb.key | gpg --dearmor > /etc/apt/trusted.gpg.d/influxdb.gpg
export DISTRIB_ID=$(lsb_release -si); export DISTRIB_CODENAME=$(lsb_release -sc)
echo "deb [signed-by=/etc/apt/trusted.gpg.d/influxdb.gpg] https://repos.influxdata.com/${DISTRIB_ID,,} ${DISTRIB_CODENAME} stable" > /etc/apt/sources.list.d/influxdb.list
```

Second, updating the packages and installation from influxDB:

```
sudo apt-get update && sudo apt-get install influxdb
```

Third, starting the influxDB service and configure it to launch at boot time:

```
sudo systemctl unmask influxdb.service
sudo systemctl start influxdb
sudo systemctl enable influxdb.service
```

#### Configuration

First, enter the influxdb CLI in your shell:

```
influx
```

Second, we create the database with the desired retention policy:

```
CREATE DATABASE mydb WITH DURATION 30d
```
