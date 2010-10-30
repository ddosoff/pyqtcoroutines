#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Qt coroutines implementation.
# GNU LGPL v. 2.1
#

import sys
import datetime
from collections import deque
from types import GeneratorType
from PyQt4.QtCore import QObject, QTimer, pyqtSignal


# Reduce scheduler overhead.
# Iterate inside Task.run, when calling subcoroutines.
MAX_TASK_ITERATIONS = 3


# Scheduler sends badTask signal
MAX_ITERATION_TIME = datetime.timedelta( milliseconds = 300 )


# Average scheduler running time between qt loop cycle
AVERAGE_SCHEDULER_TIME = datetime.timedelta( milliseconds = 30 )


# Max scheduler iterations between qt loop cycle
MAX_SCHEDULER_ITERATIONS = 10



# Usage: 
#   yield Return( v1, v2, .. )
class Return( object ):
    def __init__( self, *args ):
        if not args:
            raise Exception( "Please use 'return' keyword, instead of 'yield Return()'" )

        if len( args ) == 1:
            # v = yield subCoroutine()
            self.value = args[ 0 ]
        else:
            # a,b,c = yield subCoroutine()
            self.value = args



# Base deferred system call class
class SystemCall( QObject ):
    def handle( self ):
        raise Exception( 'Not Implemented' )



# Usage:
#   yield Sleep( 100 )   # sleep 100ms
class Sleep( SystemCall ):
    def __init__( self, ms ):
        SystemCall.__init__( self )
        self.ms = ms


    def handle( self ):
        self.startTimer( self.ms )


    def timerEvent( self, e ):
        self.task.sendval = None
        self.scheduler.schedule( self.task )



# Coroutine based task
class Task( QObject ):
    # Signals
    done = pyqtSignal( Return )

    def __init__( self, parent, coroutine ):
        QObject.__init__( self, parent )

        self.stack = deque()          # stack for subcoroutines
        self.coroutine = coroutine    # top coroutine/subcoroutine
        self.sendval = None           # value to send into coroutine


    def formatBacktrace( self ):
        # TODO: implement full trace
        return 'File "%s", line %d' % \
               (self.coroutine.gi_code.co_filename, self.coroutine.gi_frame.f_lineno)


    # Run a task until it hits the next yield statement
    def run( self ):
        i = 0
        while True:
            i += 1
            if i > MAX_TASK_ITERATIONS:
                return

            try:
                # save result into self to protect from gc
                self.result = self.coroutine.send( self.sendval )

                # simple trap? (yield)
                if self.result is None:
                    # go back to the scheduler
                    return

                # yield SystemCall(..)
                if isinstance( self.result, SystemCall ): 
                    # handled by scheduler
                    return self.result

                # yield subcoroutine(..)
                if isinstance( self.result, GeneratorType ):
                    # save current coroutine in stack
                    self.stack.append( self.coroutine )
                    self.coroutine = self.result
                    self.sendval = None
                    continue
                
                # yield Return(..)
                if isinstance( self.result, Return ):
                    raise StopIteration()

                # Unknown result type!?
                raise TypeError( '%s\n\nWrong type %s yielded.' % \
                                 (self.formatBacktrace(), type(self.result)) )
            except StopIteration:
                if not isinstance( self.result, Return ):
                    # here is old result, replace with None
                    self.result = Return( None )

                # end of task?
                if not self.stack:
                    self.done.emit( self.result )
                    del self.coroutine
                    raise

                # end of subcoroutine, return None..
                self.sendval = self.result.value
                # in case of last yield in coroutine
                # self.result never will be assigned again
                # clear it.
                self.result = Return( None )
                del self.coroutine
                self.coroutine = self.stack.pop()




class Scheduler( QObject ):
    # Signals:
    longIteration = pyqtSignal( datetime.timedelta, Task )

    # No more tasks?
    done = pyqtSignal()

    def __init__( self, parent = None ):
        QObject.__init__( self, parent )

        self.tasks = 0
        self.ready = deque()
        self.timerId = None


    # Add and schedule coroutine as Task
    def newTask( self, coroutine, parent = None ):
        if parent is None:
            parent = self
        t = Task( parent, coroutine )  
        t.destroyed.connect( self.taskDestroyed )
        self.tasks += 1
        # autorun.inf :)
        self.schedule( t )
        return t


    def schedule( self, t ):
        self.ready.appendleft( t )
        if self.timerId is None:
            self.timerId = self.startTimer( 0 )


    def taskDestroyed( self, task ):
        self.tasks -= 1


    # scheduler!
    def timerEvent( self, e ):
        # Do not iterate too much, 
        # let qt process events too.
        i = 0
        startTime = datetime.datetime.now()
        lastTime = startTime
        timeout = False
        while self.ready and not timeout:
            i += 1
            if i > MAX_SCHEDULER_ITERATIONS:
                print 'MAX_SCHEDULER_ITERATIONS exceed'
                return

            task = self.ready.pop()
            try:
                result = task.run()

                t = datetime.datetime.now()
                # scheduler is running too long? 
                if t - startTime > AVERAGE_SCHEDULER_TIME:
                    print 'scheduler(): iteration %d, execution time %s, AVERAGE_SCHEDULER_TIME exceed' % (i, t - startTime)
                    timeout = True

                # task was running too long?
                if t - lastTime > MAX_ITERATION_TIME:
                    print 'scheduler(): %s execution time incredibly long %s!' % (task, t - lastTime)
                    self.longIteration.emit( t - lastTime, task )
                
                lastTime = t
          
                if isinstance( result, SystemCall ):
                    # save task to result and process it 
                    result.task = task
                    result.scheduler = self
                    result.handle()
                    # SystemCall will resume execution 
                    # this task to ready queue
                    continue
            except StopIteration:
                self.tasks -= 1
                task.deleteLater()
                continue

            # continue this task
            self.ready.appendleft( task )

        if not self.ready:
            self.killTimer( self.timerId )
            self.timerId = None

        if not self.tasks:
            self.done.emit()



if __name__ == '__main__':
    import sys
    from PyQt4.QtGui import QApplication
    a = QApplication( sys.argv )
    s = Scheduler( a )

    # call QApplication.quit() when all coroutines done
    s.done.connect( a.quit )

    def valueReturner( name ):
        print '%s valueReturner()' % name
        v = 'valueReturner!'
        yield Return( v )
        print 'never print it'

    def multipleValueReturner( name ):
        print '%s multipleValueReturner()' % name
        v1 = 'multipleValueReturner!'
        v2 = 2
        yield Return( v1, v2 )

    def subcoroutinesTest( name ):
        print '%s subcoroutinesTest()' % name
        v1, v2 = yield multipleValueReturner( name )
        v = yield valueReturner( name )

        print '%s v = %s, v1 = %s, v2 = %s' % (name, v, v1, v2)
        yield Return( name, v, v1, v2 )
        print 'never print it'

    # test subcoroutines
    for i in range( 0, 3 ):
        lastTask = s.newTask( subcoroutinesTest('task %d' % i) )


    class TaskReturnValueTest( QObject ):
        def slotDone( self, res ):
            print 'slotDone():', res.value

    d = TaskReturnValueTest()
    lastTask.done.connect( d.slotDone )
    a.exec_()
