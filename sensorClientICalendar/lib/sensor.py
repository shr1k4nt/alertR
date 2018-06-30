#!/usr/bin/python2

# written by sqall
# twitter: https://twitter.com/sqall01
# blog: http://blog.h4des.org
# github: https://github.com/sqall01
#
# Licensed under the GNU Affero General Public License, version 3.

import time
import random
import os
import logging
import json
import icalendar
import requests
import threading
import Queue
from client import AsynchronousSender
from localObjects import SensorDataType, SensorAlert, StateChange
import subprocess


# Internal class that holds the important attributes
# for a sensor to work (this class must be inherited from the
# used sensor class).
class _PollingSensor:

	def __init__(self):

		# Id of this sensor on this client. Will be handled as
		# "remoteSensorId" by the server.
		self.id = None

		# Description of this sensor.
		self.description = None

		# Delay in seconds this sensor has before a sensor alert is
		# issued by the server.
		self.alertDelay = None

		# Local state of the sensor (either 1 or 0). This state is translated
		# (with the help of "triggerState") into 1 = "triggered" / 0 = "normal"
		# when it is send to the server.
		self.state = None

		# State the sensor counts as triggered (either 1 or 0).
		self.triggerState = None

		# A list of alert levels this sensor belongs to.
		self.alertLevels = list()

		# Flag that indicates if this sensor should trigger a sensor alert
		# for the state "triggered" (true or false).
		self.triggerAlert = None

		# Flag that indicates if this sensor should trigger a sensor alert
		# for the state "normal" (true or false).
		self.triggerAlertNormal = None

		# The type of data the sensor holds (i.e., none at all, integer, ...).
		# Type is given by the enum class "SensorDataType".
		self.sensorDataType = None

		# The actual data the sensor holds.
		self.sensorData = None

		# Flag indicates if this sensor alert also holds
		# the data the sensor has. For example, the data send
		# with this alarm message could be the data that triggered
		# the alarm, but not necessarily the data the sensor
		# currently holds. Therefore, this flag indicates
		# if the data contained by this message is also the
		# current data of the sensor and can be used for example
		# to update the data the sensor has.
		self.hasLatestData = None

		# Flag that indicates if a sensor alert that is send to the server
		# should also change the state of the sensor accordingly. This flag
		# can be useful if the sensor watches multiple entities. For example,
		# a timeout sensor could watch multiple hosts and has the state
		# "triggered" when at least one host has timed out. When one host
		# connects back and still at least one host is timed out,
		# the sensor can still issue a sensor alert for the "normal"
		# state of the host that connected back, but the sensor
		# can still has the state "triggered".
		self.changeState = None

		# Optional data that can be transfered when a sensor alert is issued.
		self.hasOptionalData = False
		self.optionalData = None

		# Flag indicates if the sensor changes its state directly
		# by using forceSendAlert() and forceSendState() and the SensorExecuter
		# should ignore state changes and thereby not generate sensor alerts.
		self.handlesStateMsgs = False


	# this function returns the current state of the sensor
	def getState(self):
		raise NotImplementedError("Function not implemented yet.")


	# this function updates the state variable of the sensor
	def updateState(self):
		raise NotImplementedError("Function not implemented yet.")


	# This function initializes the sensor.
	#
	# Returns True or False depending on the success of the initialization.
	def initializeSensor(self):
		raise NotImplementedError("Function not implemented yet.")


	# This function decides if a sensor alert for this sensor should be sent
	# to the server. It is checked regularly and can be used to force
	# a sensor alert despite the state of the sensor has not changed.
	#
	# Returns an object of class SensorAlert if a sensor alert should be sent
	# or None.
	def forceSendAlert(self):
		raise NotImplementedError("Function not implemented yet.")


	# This function decides if an update for this sensor should be sent
	# to the server. It is checked regularly and can be used to force an update
	# of the state and data of this sensor to be sent to the server.
	#
	# Returns an object of class StateChange if a sensor alert should be sent
	# or None.
	def forceSendState(self):
		raise NotImplementedError("Function not implemented yet.")


# Class that controls one icalendar.
class ICalendarSensor(_PollingSensor):

	def __init__(self):
		_PollingSensor.__init__(self)

		# Set sensor to not hold any data.
		# NOTE: Can be changed if "parseOutput" is set to true in the
		# configuration file.
		self.sensorDataType = SensorDataType.NONE

		# used for logging
		self.fileName = os.path.basename(__file__)

		# Name of the calendar.
		self.name = None

		# Location of the icalendar.
		self.location = None

		# Used htaccess authentication.
		self.htaccessAuth = None
		self.htaccessUser = None
		self.htaccessPass = None
		self.htaccessData = None

		# The interval in seconds in which an update is collected
		# from the server.
		self.interval = None

		# Number of failed calendar collection attempts.
		self.failedCounter = 0
		self.maxFailedAttempts = 10
		self.inFailedState = False

		# Locks calendar data in order to be thread safe.
		self.icalendarLock = threading.Semaphore(1)

		# Time when the last update was done.
		self.lastUpdate = 0

		# iCalendar data object.
		self.icalendar = None

		# A queue of reminder sensor alerts.
		self.reminderAlertQueue = Queue.Queue()


	# Collect calendar data from the server.
	def _getCalendar(self):

		logging.debug("[%s]: Retrieving calendar data from '%s'."
				% (self.fileName, self.location))

		# Request data from server.
		request = None
		try:
			request = requests.get(self.location,
				verify=True,
				auth=self.htaccessData)
		except:
			logging.exception("[%s]: Could not get calendar data from server."
				% self.fileName)
			self.failedCounter += 1
			return

		# Check status code.
		if request.status_code != 200:
			logging.error("[%s] Server responded with wrong status code (%d)."
				% (self.fileName, request.status_code))
			self.failedCounter += 1
			return

		# Parse calendar data.
		tempCal = None
		try:
			tempCal = icalendar.Calendar.from_ical(request.content)
		except:
			logging.exception("[%s]: Could not parse calendar data."
				% self.fileName)
			self.failedCounter += 1
			return

		# Move copy icalendar object to final object.
		self.icalendarLock.acquire()
		self.icalendar = tempCal
		self.icalendarLock.release()

		# Reset fail counter.
		self.failedCounter = 0

		# Update time.
		utcTimestamp = int(time.time())
		self.lastUpdate = utcTimestamp


	# Process the calendar data if we have a reminder triggered.
	def _processCalendar(self):
		self.icalendarLock.acquire()

		# Only process calendar data if we have any.
		if self.iCalendar is None:
			self.icalendarLock.release()
			return



		# TODO calendar data processing
		# - remember to lock access to calendar object.
		# - place sensor alert in queue: self.reminderAlertQueue



		self.icalendarLock.release()


	def initializeSensor(self):
		self.changeState = False
		self.hasLatestData = False
		self.state = 1 - self.triggerState

		# Set htaccess authentication object.
		if self.htaccessAuth == "BASIC":
			self.htaccessData = requests.auth.HTTPBasicAuth(self.htaccessUser,
				self.htaccessPass)
		elif self.htaccessAuth == "DIGEST":
			self.htaccessData = requests.auth.HTTPDigestAuth(self.htaccessUser,
				self.htaccessPass)
		elif self.htaccessAuth == "NONE":
			self.htaccessData = None
		else:
			return False

		# Get first calendar data.
		self._getCalendar()

		return True


	def getState(self):
		return self.state


	def updateState(self):

		# Check if we have to collect new calendar data. 
		utcTimestamp = int(time.time())
		if (utcTimestamp - self.lastUpdate) > self.interval:

			# Update calendar data in a non-blocking way
			# (this means also, that the current state will not be processed
			# on the updated data, but one of the next rounds will have it)
			thread = threading.Thread(target=self._getCalendar)
			thread.start()

			# Update time.
			self.lastUpdate = utcTimestamp

		# Process calendar data for occurring reminder.
		self._processCalendar()


		#print self.icalendar

		# TODO
		# - create sensor alert for reminder
		# - use queue object for sensor alerts <-- queue is already processed in forceSendAlert()
		# - remember to lock access to calendar object.
		# - remember to enter optionalData into the wiki
		

	def forceSendAlert(self):

		# Check if we have exceeded the threshold of failed calendar
		# retrieval attempts and create a sensor alert if we have.
		sensorAlert = None
		if (not self.inFailedState
			and self.failedCounter > self.maxFailedAttempts):

			sensorAlert = SensorAlert()
			sensorAlert.clientSensorId = self.id
			sensorAlert.state = 1
			sensorAlert.hasOptionalData = True
			msg = "Failed more than %d times for '%s' " \
				% (self.maxFailedAttempts, self.name) \
				+ "to retrieve calendar data."
			sensorAlert.optionalData = {"message": msg,
										"name": self.name,
										"type": "timeout"}
			sensorAlert.changeState = True
			sensorAlert.hasLatestData = False
			sensorAlert.dataType = SensorDataType.NONE

			self.state = self.triggerState
			self.inFailedState = True

		# If we are in a failed retrieval state and we could retrieve
		# calendar data again trigger a sensor alert for "normal".
		elif (self.inFailedState
			and self.failedCounter <= self.maxFailedAttempts):

			sensorAlert = SensorAlert()
			sensorAlert.clientSensorId = self.id
			sensorAlert.state = 0
			sensorAlert.hasOptionalData = True
			msg = "Calendar data for '%s' retrievable again." \
				% self.name
			sensorAlert.optionalData = {"message": msg,
										"name": self.name,
										"type": "timeout"}
			sensorAlert.changeState = True
			sensorAlert.hasLatestData = False
			sensorAlert.dataType = SensorDataType.NONE

			self.state = 1 - self.triggerState
			self.inFailedState = False

		# If we have sensor alerts of reminder waiting
		# return the oldest of them.
		elif not self.reminderAlertQueue.empty():
			try:
				sensorAlert = self.reminderAlertQueue.get(True, 2)
			except:
				pass

		return sensorAlert


	def forceSendState(self):
		return None


# this class polls the sensor states and triggers alerts and state changes
class SensorExecuter:

	def __init__(self, globalData):
		self.fileName = os.path.basename(__file__)
		self.globalData = globalData
		self.connection = self.globalData.serverComm
		self.sensors = self.globalData.sensors

		# Flag indicates if the thread is initialized.
		self._isInitialized = False


	def isInitialized(self):
		return self._isInitialized


	def execute(self):

		# time on which the last full sensor states were sent
		# to the server
		lastFullStateSent = 0

		# Get reference to server communication object.
		while self.connection is None:
			time.sleep(0.5)
			self.connection = self.globalData.serverComm

		self._isInitialized = True

		while True:

			# check if the client is connected to the server
			# => wait and continue loop until client is connected
			if not self.connection.isConnected():
				time.sleep(0.5)
				continue

			# poll all sensors and check their states
			for sensor in self.sensors:

				oldState = sensor.getState()
				sensor.updateState()
				currentState = sensor.getState()

				# Check if a sensor alert is forced to send to the server.
				# => update already known state and continue
				sensorAlert = sensor.forceSendAlert()
				if sensorAlert:
					oldState = currentState

					asyncSenderProcess = AsynchronousSender(
						self.connection, self.globalData)
					# set thread to daemon
					# => threads terminates when main thread terminates	
					asyncSenderProcess.daemon = True
					asyncSenderProcess.sendSensorAlert = True
					asyncSenderProcess.sendSensorAlertSensorAlert = sensorAlert
					asyncSenderProcess.start()

					continue

				# check if the current state is the same
				# than the already known state => continue
				elif oldState == currentState:
					continue

				# Check if we should ignore state changes and just let
				# the sensor handle sensor alerts by using forceSendAlert()
				# and forceSendState().
				elif sensor.handlesStateMsgs:
					continue

				# check if the current state is an alert triggering state
				elif currentState == sensor.triggerState:

					# check if the sensor triggers a sensor alert
					# => send sensor alert to server
					if sensor.triggerAlert:

						logging.info("[%s]: Sensor alert " % self.fileName
							+ "triggered by '%s'." % sensor.description)

						# Create sensor alert object to send to the server.
						sensorAlert = SensorAlert()
						sensorAlert.clientSensorId = sensor.id
						sensorAlert.state = 1
						sensorAlert.hasOptionalData = sensor.hasOptionalData
						sensorAlert.optionalData = sensor.optionalData
						sensorAlert.changeState = sensor.changeState
						sensorAlert.hasLatestData = sensor.hasLatestData
						sensorAlert.dataType = sensor.sensorDataType
						sensorAlert.sensorData = sensor.sensorData

						asyncSenderProcess = AsynchronousSender(
							self.connection, self.globalData)
						# set thread to daemon
						# => threads terminates when main thread terminates	
						asyncSenderProcess.daemon = True
						asyncSenderProcess.sendSensorAlert = True
						asyncSenderProcess.sendSensorAlertSensorAlert = \
							sensorAlert
						asyncSenderProcess.start()

					# if sensor does not trigger sensor alert
					# => just send changed state to server
					else:

						logging.debug("[%s]: State " % self.fileName
							+ "changed by '%s'." % sensor.description)

						# Create state change object to send to the server.
						stateChange = StateChange()
						stateChange.clientSensorId = sensor.id
						stateChange.state = 1
						stateChange.dataType = sensor.sensorDataType
						stateChange.sensorData = sensor.sensorData

						asyncSenderProcess = AsynchronousSender(
							self.connection, self.globalData)
						# set thread to daemon
						# => threads terminates when main thread terminates	
						asyncSenderProcess.daemon = True
						asyncSenderProcess.sendStateChange = True
						asyncSenderProcess.sendStateChangeStateChange = \
							stateChange
						asyncSenderProcess.start()

				# only possible situation left => sensor changed
				# back from triggering state to a normal state
				else:

					# check if the sensor triggers a sensor alert when
					# state is back to normal
					# => send sensor alert to server
					if sensor.triggerAlertNormal:

						logging.info("[%s]: Sensor alert " % self.fileName
							+ "for normal state "
							+ "triggered by '%s'." % sensor.description)

						# Create sensor alert object to send to the server.
						sensorAlert = SensorAlert()
						sensorAlert.clientSensorId = sensor.id
						sensorAlert.state = 0
						sensorAlert.hasOptionalData = sensor.hasOptionalData
						sensorAlert.optionalData = sensor.optionalData
						sensorAlert.changeState = sensor.changeState
						sensorAlert.hasLatestData = sensor.hasLatestData
						sensorAlert.dataType = sensor.sensorDataType
						sensorAlert.sensorData = sensor.sensorData

						asyncSenderProcess = AsynchronousSender(
							self.connection, self.globalData)
						# set thread to daemon
						# => threads terminates when main thread terminates	
						asyncSenderProcess.daemon = True
						asyncSenderProcess.sendSensorAlert = True
						asyncSenderProcess.sendSensorAlertSensorAlert = \
							sensorAlert
						asyncSenderProcess.start()

					# if sensor does not trigger sensor alert when
					# state is back to normal
					# => just send changed state to server
					else:

						logging.debug("[%s]: State " % self.fileName
							+ "changed by '%s'." % sensor.description)

						# Create state change object to send to the server.
						stateChange = StateChange()
						stateChange.clientSensorId = sensor.id
						stateChange.state = 0
						stateChange.dataType = sensor.sensorDataType
						stateChange.sensorData = sensor.sensorData

						asyncSenderProcess = AsynchronousSender(
							self.connection, self.globalData)
						# set thread to daemon
						# => threads terminates when main thread terminates	
						asyncSenderProcess.daemon = True
						asyncSenderProcess.sendStateChange = True
						asyncSenderProcess.sendStateChangeStateChange = \
							stateChange
						asyncSenderProcess.start()

			# Poll all sensors if they want to force an update that should
			# be send to the server.
			for sensor in self.sensors:

				stateChange = sensor.forceSendState()
				if stateChange:
					asyncSenderProcess = AsynchronousSender(
						self.connection, self.globalData)
					# set thread to daemon
					# => threads terminates when main thread terminates	
					asyncSenderProcess.daemon = True
					asyncSenderProcess.sendStateChange = True
					asyncSenderProcess.sendStateChangeStateChange = stateChange
					asyncSenderProcess.start()

			# check if the last state that was sent to the server
			# is older than 60 seconds => send state update
			utcTimestamp = int(time.time())
			if (utcTimestamp - lastFullStateSent) > 60:

				logging.debug("[%s]: Last state " % self.fileName
					+ "timed out.")

				asyncSenderProcess = AsynchronousSender(
					self.connection, self.globalData)
				# set thread to daemon
				# => threads terminates when main thread terminates	
				asyncSenderProcess.daemon = True
				asyncSenderProcess.sendSensorsState = True
				asyncSenderProcess.start()

				# update time on which the full state update was sent
				lastFullStateSent = utcTimestamp
				
			time.sleep(0.5)