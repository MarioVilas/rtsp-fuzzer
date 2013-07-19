# Simple RTSP server
# by Mario Vilas (mvilas at gmail.com)

# TO DO list:
#   [ ] Encapsulate RTSP into HTTP
#   [ ] Handle more than one message in a single UDP packet
#   [ ] Parse SDP announcements
#   [ ] Implement RDP
#   [ ] Serialize access to Transport objects

import mimebased
from mimebased import Message, StreamingFactory
from mimebased import RTSPRequest, RTSPResponse, HTTPRequest, HTTPResponse

from urlparse import urlsplit, urlunsplit
from thread import start_new_thread
from threading import Event
from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from select import select
from time import asctime

import traceback

#==============================================================================

class Transport:
    'Virtual base class for Transport objects'

    def __init__(self, sock = None):
        self.sock = sock
        if self.sock is None:
            self.create()

    def parse(self, data):
        return StreamingFactory.parse(data)

    def recursive(self, data):
        return StreamingFactory.recursive(data)

    def connect(self, address):
        print 'CONNECTING TO %s:%d' % address           # XXX
        if self.sock is None:
            self.create()
        self.address = address
        self.sock.connect(self.address)

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.sock = None

    def bind(self, mask):
        self.mask = mask
        return self.sock.bind(mask)

#------------------------------------------------------------------------------

class DatagramTransport(Transport):
    'Plain UDP transport'

    def create(self):
        self.sock = socket(AF_INET, SOCK_DGRAM)
        return self.sock

    def listen(self):
        pass

    def accept(self):
        select( [self.sock], [], [] )
        if self.sock is None:
            return
        newTransport            = self.__class__(self.sock)
##        newTransport.parserList = self.parserList
        return newTransport

    def read(self):
        data    = self.sock.recv(0x10000)
        message = self.parse(data)
        return message

    def write(self, message):
        data   = str(message)
        retval = self.sock.sendto(data, self.address)
        return retval

#------------------------------------------------------------------------------

class StreamTransport(Transport):
    'Plain TCP transport'

##    def __init__(self, sock = None):
##        Transport.__init__(self, sock)
##        self.write_buffer = ''
##
##    def feed(self, data):
##        self.write_buffer += data
##
##    def consume(self, timeout = 0.5):
##        count   = 0
##        r, w, e = select( [], [self.sock], [], timeout )
##        if self.sock in w:
##            data, self.write_buffer = self.write_buffer, ''
##            count = self.sock.send(data)
##            data  = data[:count]
##            self.write_buffer = data + self.write_buffer
##        return count

    def create(self):
        self.sock = socket(AF_INET, SOCK_STREAM)
        return self.sock

    def listen(self):
        return self.sock.listen(5)

    def accept(self):
        select( [self.sock], [], [] )
        if self.sock is None:
            return
        newSocket, peerAddress      = self.sock.accept()
        newTransport                = self.__class__(newSocket)
        newTransport.address        = peerAddress
##        newTransport.parserList     = self.parserList
        return newTransport

    def read(self):
        print 'READING'                                         # XXX
##        if self.sock is None:
##            self.connect(self.address)
        rawData = ''
        maxHeader = 0x1000
        endHeader = Message.newline * 2
        while endHeader not in rawData:
            recvSize = maxHeader - len(rawData)
            if recvSize <= 0:
                raise Exception, 'Bad header'
            newData = self.sock.recv(recvSize)
            if len(newData) == 0:
                raise Exception, 'Connection closed by peer'
            rawData += newData
        message = self.parse(rawData)
        contentLength = message.get('Content-length', '0')
        contentLength = long(contentLength)
        print 'CONTENT LENGTH %d' % contentLength               # XXX
        if contentLength > 0:
            recvSize = len(message.getData())
            missingSize = contentLength - recvSize
            print 'MISSING DATA %d' % missingSize               # XXX
            while missingSize > 0:
                newData = self.sock.recv(0x1000)
                message.appendData(newData)
                if not newData:
                    break
##            if missingSize > 0:
##                raise Exception, 'Connection closed by peer'
        return message

    def write(self, message):
##        if self.sock is None:
##            self.connect(self.address)
        data   = str(message)
        print 'WRITING %r' % data                               # XXX
        retval = self.sock.sendall(data)
        return retval

#------------------------------------------------------------------------------

class Server:
    'Base class for streaming servers'

    userAgent = 'BaseStreamingServer'

    def __init__(self, transportClass = StreamTransport,
                                    bindAddress = 'localhost', bindPort = 554):
        self.transportClass = transportClass
        self.bindAddress    = bindAddress
        self.bindPort       = bindPort
        self.alive          = True
        self.debugging      = True  # False
        self.killEvent      = Event()

    def kill(self, timeout = None):
        self.alive = False
        self.listener.close()
        return self.killEvent.wait(timeout)

    def spawn(self):
        start_new_thread(self.run, ())

    def run(self):
        try:
            self.listener = self.transportClass()
            self.listener.bind( (self.bindAddress, self.bindPort) )
            self.listener.listen()
            while self.alive:
                newTransport = self.listener.accept()
                if self.alive:
                    start_new_thread( self.serve, (newTransport,) )
##            self.listener.close()
        except:
            if self.debugging:
                traceback.print_exc()
                print
        self.killEvent.set()

    def serve(self, transport):
        try:
            while transport.sock is not None:
                req  = transport.read()
                name = 'do_%s' % req.getMethod()
                fn   = getattr(self, name, self.serveUnknown)
                resp = fn(req, transport)
                if not resp:
                    resp = self.buildErrorResponse(req, '500')
                transport.write(resp)
        except:
            if self.debugging:
                traceback.print_exc()
                print

    def serveUnknown(self, req, transport):
        return self.buildErrorResponse(req, '405')

    def buildRequest(self, method, path, data, cseq = 0, session = None):
        req = RTSPRequest()
        req.setMethod( method )
        req.setPath( path )
        req.setProtocol( req.supportedProtocols[0] )
        req.setData( data )
        req['User-Agent']       = self.userAgent
        if cseq is not None:
            req['CSeq']         = cseq
        contentLength           = len( req.getData() )
        if contentLength > 0:
            req['Content-length'] = contentLength
        if session is not None:
            req['Session']      = session
        return req

    def buildResponse(self, req, status = '200', data = ''):
##        resp = RTSPResponse()
        resp = req.makeResponse()
        resp.setStatus( status )
        resp.setProtocol( req.getProtocol() )
        resp.setText( resp.supportedCodes[ resp.getStatus() ] )
        resp.setData( data )
        if req.has_key('Cseq'):
            resp['CSeq']            = req['CSeq']
        resp['Cache-Control']       = 'no-cache'
        resp['Content-length']      = len( resp.getData() )
        resp['Date']                = asctime()
        resp['Expires']             = resp['Date']
        if req.has_key('Connection'):
            resp['Connection']      = req['Connection']
        resp['Server']              = self.userAgent
        return resp

    def buildErrorResponse(self, req, status):
        if hasattr(req.makeResponse, 'errorPage'):          # XXX ugly hack
            text = req.makeResponse.supportedCodes[status]
            data = req.makeResponse.errorPage % vars()
            return self.buildResponse(req, status, data)
        return self.buildResponse(req, status)

#------------------------------------------------------------------------------

class Client(Server):
    'Base class for streaming clients'

    userAgent = 'BaseStreamingClient'

    def connect(self, targetAddress, targetPort = 554):
        self.connection = self.transportClass()
        self.connection.connect( (targetAddress, targetPort) )

    def disconnect(self):
        c = self.connection
        del self.connection
        c.close()

#------------------------------------------------------------------------------

class Proxy(Server):
    'Base class for streaming proxies'

    userAgent = 'BaseStreamingProxy'

    def __init__(self, transportClass = StreamTransport,
                                    bindAddress = 'localhost', bindPort = 554):
        Server.__init__(self, transportClass, bindAddress, bindPort)
        self.connectionDict = {}

    def proxy_connect(self, req):
##        url = req.getURL()
        url = req.getPath()
        host = urlsplit(url)[1]
        if ':' in host:
            connectAddress, connectPort = host.split(':')
        else:
            connectAddress, connectPort = host, req.defaultPort
        connectPort = int(connectPort)
        self.changeURL(req, connectAddress, connectPort)
        key = (connectAddress, connectPort)
        if self.connectionDict.has_key(key):
            connection = self.connectionDict[key]
            if connection.sock is None:
                del self.connectionDict[key]
        if not self.connectionDict.has_key(key):
            connection = self.transportClass()
            connection.connect( (connectAddress, connectPort) )
            self.connectionDict[key] = connection
        return connection

    def proxy(self, req):
        try:
            connection = self.proxy_connect(req)
            req.append( ('Via', self.userAgent) )
            if hasattr(req, 'getRelativeURL'):
                req.setPath( req.getRelativeURL() )
            connection.write(req)
            resp = connection.read()
        except:
            if self.debugging:
                traceback.print_exc()
                print
            resp = self.buildErrorResponse(req, '502')
        return resp

    def serve(self, transport):
        try:
            while transport.sock is not None:
                req  = transport.read()
                pre  = getattr(self, 'pre_%s' % req.getMethod(),  self.preUnknown)
                post = getattr(self, 'post_%s' % req.getMethod(), self.postUnknown)
                req  = pre(req, transport)
                if req:
                    resp = self.proxy(req)
                    if resp:
                        resp = post(resp, transport)
                        if resp:
                            transport.write(resp)
                        else:
                            transport.close()
        except:
            if self.debugging:
                traceback.print_exc()
                print

    def changeURL(self, req, connectAddress, connectPort):
        url         = req.getURL()
        pieces      = list( urlsplit(url) )
        pieces[1]   = '%s:%d' % (connectAddress, connectPort)
        url         = urlunsplit( tuple(pieces) )
        req.setURL(url)
        return req

    def preUnknown(self, req, transport):
        if self.debugging:
            print '-' * 79
            print str(req)
            print '-' * 79
        return req

    def postUnknown(self, resp, transport):
        if self.debugging:
            print '-' * 79
            print str(resp)
            print '-' * 79
        return resp

#==============================================================================

def testme():
    'Some rudimentary test code'
    print 'Running.'
    proxy_tcp = Proxy(StreamTransport,   'localhost', 5454)
    proxy_udp = Proxy(DatagramTransport, 'localhost', 5455)
    print 'Starting UDP proxy...'
    proxy_udp.spawn()
    print 'Starting TCP proxy...'
    proxy_tcp.spawn()
    print 'Hit Enter to close.'
    raw_input()
    print 'Shutting down UDP proxy...'
    proxy_udp.kill()
    print 'Shutting down TCP proxy...'
    proxy_tcp.kill()
    print 'Done.'

if __name__ == '__main__':
    testme()
