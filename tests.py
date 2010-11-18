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
import hotshot
import hotshot.stats
from collections import deque
from PyQt4.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal
from coroutines import Scheduler, Sleep, AsynchronousCall, Return


class Test( QObject ):
    def __init__( self, scheduler ):
        QObject.__init__( self )
        self.scheduler = scheduler


    def prepare( self ):
        # set maximum test time
        QTimer.singleShot( 1500, self.testTimeouted )


    def testTimeouted( self ):
        print self, 'timeout!'
        QCoreApplication.instance().quit()



class SleepTest( Test ):
    def run( self ):
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



class SpeedTest( Test ):
    def __init__( self, scheduler, tasks ):
        Test.__init__( self, scheduler )
        self.tasks = tasks


    def incrementer( self ):
        self.incrementers += 1

        # counting iterations
        while self.counting:
            self.counter += 1
            yield

        self.incrementers -= 1


    def run( self ):
        self.counter = 0
        self.counting = True
        self.incrementers = 0

        for i in xrange( self.tasks ):
            self.scheduler.newTask( self.incrementer() )

        QTimer.singleShot( 1000, self.measure )


    def measure( self ):
        print 'Running %d tasks, %d iterations per second...' % (self.incrementers, self.counter)
        self.counting = False



class AsyncCallTest( Test ):
    def run( self ):
        # must correctly return argument value
        # and throw exception, when argument Exception.
        class Returner( AsynchronousCall ):
            def __init__( self, val ):
                self.val = val
            def handle( self ):
                self.wakeup( self.val )


        # all instances should be deleted
        class CheckMem( AsynchronousCall ):
            def __init__( self, test ):
                AsynchronousCall.__init__( self )
                self.val = 0
                self.test = test
                self.test.counter += 1
            def __del__( self ):
                self.test.counter -= 1
            def handle( self ):
                self.val += 1
                assert self.val == 1
                self.wakeup( self.val )


        def simple():
            for i in xrange( 10 ):
                res = yield Return( i )
                assert res == i


        def multiple():
            v1, v2, v3 = yield Returner( (1, 2, 3) )
            assert v1 == 1
            assert v2 == 2
            assert v3 == 3


        def exception():
            try:
                yield Returner( Exception('oops') )
                assert False
            except Exception, e:
                assert str(e) == 'oops'


        def checkMem(test):
            for i in xrange( 10 ):
                yield CheckMem(test)

        
        def counterChecker( test ):
            # assume, that all checkMems will done faster :)
            yield Sleep( 100 )
            assert not test.counter


        self.scheduler.newTask( simple() )
        self.scheduler.newTask( multiple() )
        self.scheduler.newTask( exception() )
        self.counter = 0
        for i in xrange( 10 ):
            self.scheduler.newTask( checkMem(self) )
        self.scheduler.newTask( counterChecker(self) )


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
        self.test = None
        self.scheduler = scheduler
        scheduler.done.connect( self.nextTest )
        print 'Running tests:'
        print
        QTimer.singleShot( 0, self.nextTest )


    def nextTest( self ):
        if not self.tests:
            assert not self.scheduler.tasks
            print 'Bye bye.'
            QCoreApplication.instance().quit()
            return

        # remove old test
        if self.test:
            self.test.deleteLater()

        # protect test from gc into self..
        self.test = self.tests.pop()

        assert not self.scheduler.tasks
        self.test.prepare()
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
    tester = Tester( s )
    tester.addTest( SleepTest(s) )
    tester.addTest( SpeedTest(s, 1) )
    tester.addTest( SpeedTest(s, 100) )
    tester.addTest( AsyncCallTest(s) )

    prof = hotshot.Profile("coroutines.prof")
    prof.runcall( a.exec_ )
    prof.close()
    print
    print 'Calc profiling stats...'
    stats = hotshot.stats.load("coroutines.prof")
    stats.strip_dirs()
    stats.sort_stats('time', 'calls')
    stats.print_stats(20)
