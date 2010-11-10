#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# PyQt4 coroutines tests.
#
# GNU LGPL v. 2.1
# Kirill Kostuchenko <ddosoff@gmail.com>
#
# Sorry, we can't use unittest,
# due to qt event loop.
import sys
import traceback
import datetime
from collections import deque
from PyQt4.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal
from coroutines import Scheduler, Sleep


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
            yield Sleep( sleepMs )


        self.tasks = 0
        self.start = datetime.datetime.now()
        for ms in ( 10, 0, 300, 100 ):
            self.tasks += 1

            t = self.scheduler.newTask( sleeper(ms) )
            t.ms = ms
            t.done.connect( self.checkRuntime )


    def checkRuntime( self ):
        task = self.sender()
        self.tasks -= 1

        now = datetime.datetime.now()

        # big time difference?
        mustInterval = datetime.timedelta( milliseconds = task.ms )
        assert now - self.start > mustInterval
        assert now - self.start < mustInterval + datetime.timedelta( milliseconds = 10 )

        # no more sleeper's?
        if not self.tasks:
            self.done.emit()


# TODO:)...
class ReturnValueTest( Test ):
    pass



class ReturnValuesTest( Test ):
    pass



class DoneReturnValueTest( Test ):
    pass



class DoneReturnValuesTest( Test ):
    pass



class SubcoroutinesTest( Test ):
    pass



class ExceptionRoutingTest( Test ):
    pass



class EventLoopExceptionTest( Test ):
    pass



class Tester( QObject ):
    def __init__( self, scheduler ):
        QObject.__init__( self )
        self.tests = deque()
        self.scheduler = scheduler
        scheduler.done.connect( self.allDone )
        self.deleteIteration = True
        self.schedulerDone = False
        QTimer.singleShot( 0, self.nextTest )
        print 'Running tests:'
        print


    def nextTest( self ):
        if not self.tests and self.deleteIteration:
            print
            print 'All tests done!'
            print 'Delete iteration..'
            self.deleteIteration = False
            # scheduler should not sent done signal yet
            assert not self.schedulerDone
            # let qt deleteLater all tasks and stop the scheduler.
            QTimer.singleShot( 10, self.nextTest )
            return
        elif not self.deleteIteration: 
            assert not self.scheduler.tasks
            assert self.schedulerDone
            print 'Bye bye.'
            QCoreApplication.instance().quit()
            return

        # protect test from gc into self..
        self.test = self.tests.pop()
        self.test.done.connect( self.nextTest )
        print 'Run', self.test
        self.test.run()


    def allDone( self ):
        print 'Scheduler done.'
        self.schedulerDone = True


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
    tester = Tester( s )
    tester.addTest( SleepTest(s) )
    a.exec_()
