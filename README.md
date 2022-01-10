# Raspberry Pi Indoor Air Quality Monitor

Objective of this repository is to provide code and instruction on how to turn your Raspberry Pi into an air measuring device. Given the correlation of Covid-19 particale density due to breathing and CO2, this can be be used (without warranty) as an indicator when the room needs ventilation. 



|  ![Visualization](https://github.com/TJKlein/Raspi_AirQualityMonitor/blob/main/images/screenshot01.png)
|:--:| 
| Visualization of air quality |





|  ![Photo of Rasperry Pi Setup](https://github.com/TJKlein/Raspi_AirQualityMonitor/blob/main/images/raspi_setup.png)
|:--:| 
| Photo of setup with LCD screen |



Disclaimer: This tutorial is in parts based on the [Unravel Github Repository](https://github.com/UnravelTEC/Raspi-Driver-SCD30).

## Hardware Requirements:
- [Raspberry Pi 4](https://www.raspberrypi.org/)
- [SCD30 Air Quality Sensor](https://www.sensirion.com/en/environmental-sensors/carbon-dioxide-sensors/carbon-dioxide-sensors-scd30/) or the [Seed Studio version (with Grove connector)](https://www.seeedstudio.com/Grove-CO2-Temperature-Humidity-Sensor-SCD30-p-2911.html)
- [5" LCD Display](https://www.waveshare.com/product/displays/lcd-oled/lcd-oled-1/5inch-hdmi-lcd-b-with-bicolor-case.htm)

## Software Requirements

- [Python 3](https://www.python.org/downloads/)
- [crcmod](http://crcmod.sourceforge.net/)
- [pigpio](https://abyz.me.uk/rpi/pigpio/pigpiod.html)
- [InfluxDB](https://www.influxdata.com/)
- [Grafana](https://grafana.com/)


## Hardware Setup

|  ![Raspi SDC30 Wiring](https://github.com/TJKlein/Raspi_AirQualityMonitor/blob/main/images/Raspi-wiring.png)
|:--:| 
| Illustration of how to connect the SCD30 (Seed Studio) with Grove connector to Raspberry Pi |

Once you have connected your SCD30 to the Raspberry Pi, you can verify if it can be found:

```shell
i2cdetect -y 1 0x61 0x61
```

If everything was wired correctly, this should appear in the terminal:

```shell
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                                                 
10:                                                 
20:                                                 
30:                                                 
40:                                                 
50:                                                 
60:    61                                           
70:                        
```

### GPIO Control

The SDC30 is connected to the Raspberry via the GPIO IC2 bus. To control the GPIO we need the [pigpio](https://abyz.me.uk/rpi/pigpio/pigpiod.html) library. To install the library:

```shell
wget https://github.com/joan2937/pigpio/archive/master.zip
unzip master.zip
cd pigpio-master
make
sudo make install
```

In order to launch the pigpio daemon launch:
```
sudo pigpiod
```

If everything is installed and working properly, the following command should return some integer value:
```
pigs hwver
```

### I2C Clock stretching

In I2C communication, the master device determines the clock speed. However, there are situations where an I2C slave is not able to co-operate at the clock speed determined by the master device. To faciliate communication under these circumstances the clock speed needs to slow down. The mechanism behind this slow-down is referred to as clock stretching. For communicating with the SDC30, we need the clock cycles to be stretched to 200ms. To do so, we need a little tool.

First, clone the resposity from Github:

```
https://github.com/raspihats/raspihats/tree/master/clk_stretch
```

Second, compile the source code:

```
gcc -o i2c1_set_clkt_tout i2c1_set_clkt_tout.c
gcc -o i2c1_get_clkt_tout i2c1_get_clkt_tout.c
```

In order to stretch the clock cycle to 200 ms, run the following command:

```
./i2c1_set_clkt_tout 20000
```

## Software Setup

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

### Dashboard Setup

In order to visualize the air quality measurement data we use [Grafana](https://grafana.com/).  Grafana is an open source analytics and interactive visualization.


#### Installation

Detailed instructions on how to install Grafana on a Raspberry Pi can be found [here](https://grafana.com/tutorials/install-grafana-on-raspberry-pi/)

First, we need add an authentication key to apt as well as adding the path to it:

```
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
```

Second, we install Grafana. In case you followed the steps above, you don't need to update the apt packages again (so you can omit the first command), and directly install:

```
sudo apt-get update
sudo apt-get install -y grafana
```

Third, we configure the Grafana service to launch at boot time and start the service:

```
sudo /bin/systemctl enable grafana-server
sudo /bin/systemctl start grafana-server
```

Now, we opening the browser and enter http://localhost:3000, you should see the Grafana login page. 

#### Dashboard Configuration
In the directory './Grafana' you will find configurations of dashboars that visualize the sensor readings. These can be adapted easily to change the style. To import them, simply click on import and select the JSON files one by one. Here we have three dashboards. One for temperature, one for CO_2 level and an overview dashboard.

|  ![Grafana JSON Dashboard Import](https://github.com/TJKlein/Raspi_AirQualityMonitor/blob/main/images/Import_JSON.png)
|:--:| 
| Grafana dashboard import from JSON file. |
