# Simple RTSP server
# by Mario Vilas (mvilas at gmail.com)

from mimebased import Message, RTSPRequest, RTSPResponse

from urlparse import urlsplit, urlunsplit
from thread import start_new_thread
from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from select import select

#==============================================================================

class BaseTransport:
    input_parser    = Message
    output_parser   = Message

    def __init__(self, sock = None):
        self.sock = sock
        if self.sock is None:
            self.create()

    def connect(self, address):
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

class DatagramTransport(BaseTransport):

    def create(self):
        self.sock = socket(AF_INET, SOCK_DGRAM)
        return self.sock

    def listen(self):
        pass

    def accept(self):
        select( [self.sock], [], [] )
        newTransport                = self.__class__()
        newTransport.input_parser   = self.input_parser
        newTransport.output_parser  = self.output_parser
        newTransport.connect(self.address)
        return newTransport

    def read(self):
        data    = self.sock.recv(0x10000)
        message = self.input_parser(data)
        return message

    def write(self, message):
        if isinstance(message, self.output_parser):
            data    = str(message)
        else:
            data    = message
            message = self.output_parser(data)
        retval = self.sock.sendto(data, self.address)
        if message.get('Connection', 'close') == 'close':
            self.close()
        return retval

#------------------------------------------------------------------------------

class StreamTransport(BaseTransport):

    def create(self):
        self.sock = socket(AF_INET, SOCK_STREAM)
        return self.sock

    def listen(self):
        return self.sock.listen(5)

    def accept(self):
        newSocket, peerAddress      = self.sock.accept()
        newTransport                = self.__class__(newSocket)
        newTransport.address        = peerAddress
        newTransport.input_parser   = self.input_parser
        newTransport.output_parser  = self.output_parser
        return newTransport

    def read(self):
        if self.sock is None:
            self.connect(self.address)
        rawData = ''
        maxHeader = 0x1000
        endHeader = self.input_parser.newline * 2
        while endHeader not in rawData:
            recvSize = maxHeader - len(rawData)
            if recvSize <= 0:
                raise Exception, 'Bad header'
            newData = self.sock.recv(recvSize)
            if len(newData) == 0:
                raise Exception, 'Connection closed by peer'
            rawData += newData
        message = self.input_parser(rawData)
        contentLength = message.get('Content-length', 0)
        if contentLength > 0:
            recvSize = contentLength - len(message.getData())
            while recvSize > 0:
                newData = self.sock.recv(0x1000)
                message.appendData(newData)
                if not newData:
                    break
            if recvSize > 0:
                raise Exception, 'Connection closed by peer'
        return message

    def write(self, message):
        if self.sock is None:
            self.connect(self.address)
        if isinstance(message, self.output_parser):
            data    = str(message)
        else:
            data    = message
            message = self.output_parser(data)
        retval = self.sock.sendall(data)
        if message.get('Connection', 'close') == 'close':
            self.close()
        return retval

#------------------------------------------------------------------------------

class Client:

    def __init__(self, transportClass, targetAddress = 'localhost',
                                                             targetPort = 554):
        self.transportClass = transportClass
        self.targetAddress  = targetAddress
        self.targetPort     = targetPort

    def connect(self):
        self.cseq = 0
        self.connection = self.transportClass()
        self.connection.input_parser  = RTSPRequest
        self.connection.output_parser = RTSPResponse
        self.connection.connect( (self.targetAddress, self.targetPort) )

    def close(self):
        c = self.connection
        del self.connection
        c.close()

#------------------------------------------------------------------------------

class Server:

    def __init__(self, transportClass, bindAddress = 'localhost',
                                                               bindPort = 554):
        self.transportClass = transportClass
        self.bindAddress    = bindAddress
        self.bindPort       = bindPort
        self.alive          = True

    def run(self):
        self.listener = self.transportClass()
        self.listener.input_parser  = RTSPRequest
        self.listener.output_parser = RTSPResponse
        self.listener.bind( (self.bindAddress, self.bindPort) )
        self.listener.listen()
        while self.alive:
            newTransport                = self.listener.accept()
            newTransport.input_parser   = RTSPRequest
            newTransport.output_parser  = RTSPResponse
            start_new_thread(self.serve, ())
        self.listener.close()

    def serve(self, transport):
        while transport.sock is not None:
            req  = transport.read()
            fn   = getattr(self, 'do_%s' % req.getMethod(), self.serveUnknown)
            resp = fn(req, transport)
            if not resp:
                resp = self.buildResponse(req, '500')
            transport.write(resp)

    def serveUnknown(self, req):
        return self.buildResponse(req, '405')

    def buildResponse(self, req, status = '200', data = ''):
        resp = RTSPResponse()
        resp.setStatus( status )
        resp.setProtocol( req.getProtocol() )
        resp.setText( req.supportedCodes[ resp.getStatus() ] )
        resp.setData( data )
        resp['Content-length']  = len( resp.getData() )
        resp['Connection']      = req.get('Connection', 'persistent')
        resp['CSeq']            = req.get('CSeq', 0)
        return resp

#------------------------------------------------------------------------------

class Proxy(Server):

    def __init__(self, transportClass, connectAddress, connectPort = 554,
                                    bindAddress = 'localhost', bindPort = 554):
        Server.__init__(self, transportClass, bindAddress, bindPort)
        self.connectAddress = connectAddress
        self.connectPort    = connectPort

    def proxy(self, req):
        transport               = self.transportClass()
        transport.input_parser  = RTSPRequest
        transport.output_parser = RTSPResponse
        transport.connect( (self.connectAddress, self.connectPort) )
        transport.write(req)
        resp = transport.read()
        return resp

    def serve(self):
        while transport.sock is not None:
            req  = transport.read()
            pre  = getattr(self, 'pre_%s' % req.getMethod(),  self.preUnknown)
            post = getattr(self, 'post_%s' % req.getMethod(), self.postUnknown)
            req  = pre(req)
            if req:
                resp = self.proxy(req)
                if resp:
                    resp = post(resp)
                    if resp:
                        transport.write(resp)
                    else:
                        transport.close()

    def changeURL(self, req):
        url         = req.getURL()
        pieces      = list( urlsplit(url) )
        pieces[1]   = '%s:%d' % (self.connectAddress, self.connectPort)
        url         = urlunsplit( tuple(pieces) )
        req.setURL(url)
        return req

    def preUnknown(self, req):
        req = self.changeURL(req)
        print '-' * 79
        print str(req)
        print '-' * 79
        return req

    def postUnknown(self, resp):
        print '-' * 79
        print str(resp)
        print '-' * 79
        return resp

#==============================================================================

def testme():
    proxy_tcp = Proxy(StreamTransport,   'localhost', 554, 'localhost', 555)
    proxy_udp = Proxy(DatagramTransport, 'localhost', 554, 'localhost', 555)
    start_new_thread(proxy_tcp.run, ())
    start_new_thread(proxy_udp.run, ())
    print 'Hit Enter to close'
    raw_input()

if __name__ == '__main__':
    testme()
