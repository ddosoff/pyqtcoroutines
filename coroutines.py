#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# PyQt4 based coroutines implementation.
#
# GNU LGPL v. 2.1
# Kirill Kostuchenko <ddosoff@gmail.com>

import sys
import datetime
import traceback
from collections import deque
from types import GeneratorType
from PyQt4.QtCore import QObject, QTimer, pyqtSignal


# Reduce scheduler overhead
# Iterate in the Task.run, while calling subcoroutines
MAX_TASK_ITERATIONS = 3


# Scheduler longIteration signal warning
MAX_ITERATION_TIME = datetime.timedelta( milliseconds = 300 )


# Average scheduler runtime between qt loops
AVERAGE_SCHEDULER_TIME = datetime.timedelta( milliseconds = 30 )


# Max scheduler iterations between qt loops
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



# Inherit your asynchronous calls,
# like Sleep below.
class AsynchronousCall( QObject ):
    def handle( self ):
        raise Exception( 'Not Implemented' )
    

    # will be called by scheduler, before handle()
    def setContext( self, task, scheduler ):
        self.task = task
        self.scheduler = scheduler


    # continue execution
    def wakeup( self, result = None ):
        if isinstance( result, Exception ):
            # CoException has additional field to
            # save subcoroutines stack
            e = CoException( result )
            # exception is not raised naturally, format top of the stack manually
            e.updateStack( traceback.format_stack( limit = 2 )[ -2 ] )
            self.task.exception = e
        else:
            self.task.sendval = result

        # Wake up execution of the caller's task
        self.scheduler.schedule( self.task )



# Asynchronous call example
#
# Usage:
#   yield Sleep( 100 )   # sleep 100ms
class Sleep( AsynchronousCall ):
    def __init__( self, ms ):
        AsynchronousCall.__init__( self )
        # save params for the future use
        self.ms = ms


    def handle( self ):
        # QObject is the QT library class. SytemCall inherits QObject.
        # QObject.timerEvent will be called after self.ms milliseconds
        self.timerId = QObject.startTimer( self, self.ms )


    # This is overloaded QObject.timerEvent
    # and will be called by the Qt event loop.
    def timerEvent( self, e ):
        QObject.killTimer( self, self.timerId )
        self.wakeup( None )



# due to own Coroutines stack, we
# must construct backtrace manually.
class CoException( Exception ):
    def __init__( self, orig ):
        self.tb = deque()
        self.orig = orig

    
    def updateStack( self, preformatted = None ):
        if preformatted:
            self.tb.appendleft( preformatted )
        else:
            self.tb.appendleft( traceback.format_tb( sys.exc_traceback )[-1] )



# Coroutine based task
class Task( QObject ):
    done = pyqtSignal( Return )

    def __init__( self, parent, coroutine ):
        QObject.__init__( self, parent )

        self.stack = deque()          # stack for subcoroutines
        self.coroutine = coroutine    # task coroutine / top subcoroutine
        self.sendval = None           # value to send into coroutine
        self.exception = None         # save exceptions here
        self.result = Return( None )  # default return value


    def formatBacktrace( self ):
        # TODO: implement full trace
        return 'File "%s", line %d' % \
               (self.coroutine.gi_code.co_filename, self.coroutine.gi_frame.f_lineno)


    # Run a task until it hits the next yield statement
    def run( self ):
        for i in xrange( MAX_TASK_ITERATIONS ):
            try:
                if self.exception:
                    self.result = self.coroutine.throw( self.exception.orig )
                    self.exception = None
                else:
                    # save result into self to protect from gc
                    self.result = self.coroutine.send( self.sendval )

                # simple trap? (yield)
                if self.result is None:
                    # go back to the scheduler
                    return

                # yield AsynchronousCall(..)
                if isinstance( self.result, AsynchronousCall ): 
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
                    # replace previous yield
                    self.result = Return( None )

                # end of task?
                if not self.stack:
                    self.done.emit( self.result )
                    raise

                # end of subcoroutine
                self.sendval = self.result.value
                del self.coroutine
                self.coroutine = self.stack.pop()

            except Exception, e:
                if self.exception is None:
                    self.exception = CoException( e )

                # exception was catched, but new one raised?
                if self.exception.orig != e:
                    self.exception = CoException( e )

                # calc own backtrace
                self.exception.updateStack()

                if not self.stack:
                    # exceptions must be handled in the Task coroutine
                    raise self.exception

                del self.coroutine
                self.coroutine = self.stack.pop()
                


class Scheduler( QObject ):
    longIteration = pyqtSignal( datetime.timedelta, Task )
    done = pyqtSignal()

    def __init__( self, parent = None ):
        QObject.__init__( self, parent )

        self.tasks = 0
        self.ready = deque()
        self.timerId = None
        self.printCoException = True


    # Schedule coroutine as Task
    def newTask( self, coroutine, parent = None ):
        if parent is None:
            parent = self

        t = Task( parent, coroutine )  
        t.destroyed.connect( self.taskDestroyed )
        self.tasks += 1

        self.schedule( t )
        return t


    def schedule( self, t ):
        self.ready.appendleft( t )

        if self.timerId is None:
            self.timerId = self.startTimer( 0 )


    def taskDestroyed( self, task ):
        self.tasks -= 1

        if not self.tasks:
            self.done.emit()


    def checkRuntime( self, task ):
        t = datetime.datetime.now()
        l = self.lastIterationTime
        self.lastIterationTime = t

        # task iteration too long?
        if t - l > MAX_ITERATION_TIME:
            self.longIteration.emit( t - l, task )
            return True

        # scheduler iterating too long? 
        if t - self.startIterationTime > AVERAGE_SCHEDULER_TIME:
            return True
        
        return False


    # The scheduler loop!
    def timerEvent( self, e ):
        # Do not iterate too much.. 
        self.startIterationTime = datetime.datetime.now()
        self.lastIterationTime = self.startIterationTime
        timeout = False
        for i in xrange( MAX_SCHEDULER_ITERATIONS ):
            if timeout or not self.ready:
                break

            task = self.ready.pop()
            try:
                result = task.run()
                
                if isinstance( result, AsynchronousCall ):
                    result.setContext( task, self )
                    result.handle()

                    # AsynchronousCall will resume execution later
                    continue
                     
            except Exception, e:
                task.deleteLater()

                if isinstance( e, StopIteration ):
                    continue

                if isinstance( e, CoException ) and self.printCoException:
                    sys.stdout.write( '\nUNHANDLED COROUTINE EXCEPTION BACKTRACE (self.printCoException is True)!\n')
                    for l in e.tb:
                        sys.stdout.write( l )
                    strExc = str(e.orig)
                    sys.stdout.write( strExc + '\n' + '-' * len(strExc) + '\n\n' )

                # this is unknown exception!
                # stop iterating timer, if all tasks done
                if not self.ready:
                    self.killTimer( self.timerId )
                    self.timerId = None

                # forward exception to the main event loop
                raise

            finally:
                timeout = self.checkRuntime( task )

            # continue this task later
            self.ready.appendleft( task )

        # do not lopp, if all tasks done
        if not self.ready:
            self.killTimer( self.timerId )
            self.timerId = None
            return



if __name__ == '__main__':
    import sys
    import random
    from PyQt4.QtGui import QApplication


    def valueReturner( name ):
        print '%s valueReturner()' % name
        v = 'valueReturner!'
        yield Return( v )
        print 'never print it'


    def multipleValueReturner( name ):
        print '%s multipleValueReturner()' % name
        v1 = 'multipleValueReturner!'
        v2 = 2

        # exception test
        if not random.randint( 0, 2 ):
            raise Exception( 'multipleValueReturner ooops!' )

        yield Return( v1, v2 )


    def subcoroutinesTest( name ):

        # Sleep system call example
        ms = random.randint( 1000, 2000 )
        print '%s Sleep( %d )' % (name, ms)
        yield Sleep( ms )

        # exception test
        try:
            print '%s subcoroutinesTest()' % name

            # return values and subcoroutines test
            v1, v2 = yield multipleValueReturner( name )
            v = yield valueReturner( name )
        except Exception, e:
            print "%s exception '%s' handled!" % (name, e )
        else:
            print '%s v = %s, v1 = %s, v2 = %s' % (name, v, v1, v2)

            # signal done test
            yield Return( name, v, v1, v2 )


    class TaskReturnValueTest( QObject ):
        def slotDone( self, res ):
            print 'slotDone():', res.value


    a = QApplication( sys.argv )
    s = Scheduler( a )

    # call QApplication.quit() when all coroutines done
    s.done.connect( a.quit )

    d = TaskReturnValueTest()

    # start tasks
    for i in range( 0, 3 ):
        t = s.newTask( subcoroutinesTest('task %d' % i) )
        t.done.connect( d.slotDone )

    # start qt event loop
    a.exec_()
