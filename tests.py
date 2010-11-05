#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# PyQt4 coroutines tests.
#
# GNU LGPL v. 2.1
# Kirill Kostuchenko <ddosoff@gmail.com>
#
# Sorry, we can't use elegance of the unittest,
# due to event looped qt application.
import sys
import traceback
from collections import deque
from PyQt4.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal
from qtcoroutines import Scheduler, Sleep


class Test( QObject ):
    done = pyqtSignal()
    error = pyqtSignal()

    def __init__( self, scheduler ):
        QObject.__init__( self )
        self.scheduler = scheduler


    def testTimeouted( self ):
        print self, 'timeout!'
        QCoreApplication.instance().quit()



class SleepTest( Test ):
    def run( self ):
        # set maximum test timeout
        QTimer.singleShot( 1000, self.testTimeouted )


        def sleeper( sleepMs ):
            print 'sleeper( %d ): start' % sleepMs
            yield Sleep( sleepMs )
            print 'sleeper( %d ): done' % sleepMs


        self.tasks = 0
        for ms in ( 10, 0, 300, 100 ):
            self.tasks += 1

            t = self.scheduler.newTask( sleeper(ms) )
            t.ms = ms
            t.done.connect( self.checkRuntime )


    def checkRuntime( self ):
        print 'checkRuntime', self.sender()
        self.tasks -= 1

        if not self.tasks:
            self.done.emit()



class Tester( QObject ):
    def __init__( self ):
        QObject.__init__( self )
        self.tests = deque()
        QTimer.singleShot( 0, self.nextTest )


    def nextTest( self ):
        if not self.tests:
            print 'No more tests, bye bye.'
            QCoreApplication.instance().quit()
            return

        # protect test from gc into self..
        self.test = self.tests.pop()
        self.test.done.connect( self.nextTest )
        print 'Run', self.test
        self.test.run()


    def addTest( self, test ):
        self.tests.append( test )



class TestApp( QCoreApplication ):
    def __init__( self ):
        QCoreApplication.__init__( self, sys.argv )

        sys.excepthook = self.excepthook


    def excepthook( self, type, value, tb ):
        e = ''.join(traceback.format_exception(type, value, tb))
        print
        print 'Unhandled event loop exception!'
        print e
        QCoreApplication.instance().quit()



if __name__ == '__main__':
    a = TestApp()
    s = Scheduler()
    tester = Tester()
    tester.addTest( SleepTest(s) )
    a.exec_()
