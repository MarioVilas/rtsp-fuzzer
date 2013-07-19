# Parsers for MIME based protocols
# by Mario Vilas (mvilas at gmail.com)

from urlparse import urlparse, urlsplit, urlunparse, urlunsplit

#------------------------------------------------------------------------------

class Headers:
    newline             = '\r\n'
    header_separator    = ':'
    header_fmt          = '%(name)s%(separator)s %(value)s'
    value_separator     = ';'

    supportedHeaders    = tuple()

    def normalize_header(self, header):
        return header.lower()

    def is_last_header(self, line):
        return not line.strip()

    def is_multi_line_header(self, line):
        return line.strip().endswith(self.value_separator)

    def __init__(self, data = None):
        if data is None:
            data = self.newline
        self.__headerDict  = {}
        self.__headerList  = []
        headerCache = ''
        beginLine = True
        for line in data.split(self.newline):
            headerCache += line + self.newline
            if self.is_last_header(line):
                break
            if beginLine:
                spline = line.split(self.header_separator)
                name  = spline[0]
                value = self.header_separator.join(spline[1:])
                name  = name.strip()
                value = value.strip()
            else:
                name  = self.__headerList[-1][0]
                value = line.strip()
            self.append( (name, value) )
            beginLine = not self.is_multi_line_header(line)
        self.__headerCache = headerCache

    def __str__(self):
        if self.__headerCache is None:
            self.__headerCache = ''
            separator = self.header_separator
            for name, value in self.__headerList:
                self.__headerCache += self.header_fmt % vars()
                self.__headerCache += self.newline
            self.__headerCache += self.newline
        return self.__headerCache

    def __len__(self):
        return len(str(self))

    def count(self):
        return len(self.__headerList)

    def mincount(self):
        return len(self.__headerDict)

    def get(self, name, *default):
        return self.__headerDict.get(self.normalize_header(name), *default)

    def has_key(self, name):
        return self.__headerDict.has_key(self.normalize_header(name))

    __contains__ = has_key

    def __iter__(self):
        return self.__headerList.__iter__()

    def iteritems(self):
        return self.__headerDict.iteritems()

    def iterkeys(self):
        return self.__headerDict.iterkeys()

    def itervalues(self):
        return self.__headerDict.itervalues()

    def __getslice__(self, i, j):
        return self.__headerList[i:j]

    def __getitem__(self, name):
        return self.__headerDict[self.normalize_header(name)]

    def __setitem__(self, name, value):
        if self.has_key(name):
            del self[name]
        self.append( (name, value) )

    def __delitem__(self, name):
        self.__headerCache = None
        name = self.normalize_header(name)
        del self.__headerDict[name]
        i = 0
        while i < len(self.__headerList):
            this_name = self.normalize_header(self.__headerList[i][0])
            if this_name == name:
                del self.__headerList[i]
            else:
                i += 1

    def insert(self, index, (name, value) ):
        self.__headerCache = None
        self.__headerList.insert(index, (name, value))
        value = ''
        for n, v in self.__headerList:
            if n == name:
                value += self.value_separator + v
        if value.startswith(self.value_separator):
            value = value[2:]
        self.__headerDict[self.normalize_header(name)] = value

    def append(self, (name, value) ):
        self.__headerCache = None
        self.__headerList.append( (name, value) )
        normal_name = self.normalize_header(name)
        if self.__headerDict.has_key(normal_name):
            self.__headerDict[normal_name] += self.value_separator + value
        else:
            self.__headerDict[normal_name] = value

    def validate(self):
        for header in self.iterkeys():
            if header not in self.supportedHeaders:
                return False
        return True

#------------------------------------------------------------------------------

class Message(Headers):

    def __init__(self, data = None):
        self.supportedHeaders = tuple([self.normalize_header(x) \
                                               for x in self.supportedHeaders])
        if data is None:
            data = self.newline * 2
        lineEnd     = data.find(self.newline)
        headerBegin = lineEnd + len(self.newline)
        self.setLine(data[:lineEnd])
        Headers.__init__(self, data[headerBegin:])
        self.setData('')
        dataBegin = headerBegin + len(self)
        self.setData(data[dataBegin:])

    def __str__(self):
        return self.getLine() + self.newline + Headers.__str__(self) + self.getData()

    def getLine(self):          return self.__line
    def setLine(self, line):    self.__line = line

    def getData(self):          return self.__data
    def setData(self, data):    self.__data  = data
    def appendData(self, data): self.__data += data

    def validate(self):
        extended = self.normalize_header('X-')
        for header in self.iterkeys():
            if not header.startswith(extended) and \
                                           header not in self.supportedHeaders:
                return False
        return True

#------------------------------------------------------------------------------

class Request(Message):
    supportedProtocols  = tuple()
    supportedMethods    = tuple()

    def isRequest(self):    return True
    def isResponse(self):   return False

    def setLine(self, line):
        Message.setLine(self, line)
        method, path, protocol = line.split(' ')
        self.setMethod(method)
        self.setPath(path)
        self.setProtocol(protocol)

    def getMethod(self):    return self.__method
    def getPath(self):      return self.__path
    def getProtocol(self):  return self.__protocol

    def setMethod(self, method):        self.__method   = method
    def setPath(self, path):            self.__path     = path
    def setProtocol(self, protocol):    self.__protocol = protocol

    getURL = getPath
    setURL = setPath

    @classmethod
    def identify(self, data):
        data = data[:data.find(self.newline)]
        protocol = data[data.rfind(' ')+1:]
        return protocol in self.supportedProtocols

    def validate(self):
        return (
                self.getProtocol() in self.supportedProtocols and
                self.getMethod() in self.supportedMethods and
                Message.validate(self)
                )

#------------------------------------------------------------------------------

class Response(Message):
    supportedProtocols  = tuple()
    supportedCodes      = dict()

    def isRequest(self):    return False
    def isResponse(self):   return True

    def getLine(self):
        return '%s %s %s' % (
            self.getProtocol(),
            self.getStatus(),
            self.getText(),
        )

    def setLine(self, line):
        if line:
            protocol, status, text = line.split(' ')
        else:
            protocol, status, text = '', '', ''
        self.setProtocol(protocol)
        self.setStatus(status)
        self.setText(text)

    def getProtocol(self):  return self.__protocol
    def getStatus(self):    return self.__status
    def getText(self):      return self.__text

    def setProtocol(self, protocol):    self.__protocol = protocol
    def setStatus(self, status):        self.__status   = status
    def setText(self, text):            self.__text     = text

    @classmethod
    def identify(self, data):
        data = data[:data.find(self.newline)]
        protocol = data[:data.find(' ')]
        return protocol in self.supportedProtocols

    def validate(self):
        return (
                self.getProtocol() in self.supportedProtocols and
                self.supportedCodes.has_key( self.getStatus() ) and
                Message.validate(self)
                )

#------------------------------------------------------------------------------

class ReadMail(Message):

    def __init__(self, data = None):
        self.supportedHeaders = tuple([self.normalize_header(x) \
                                               for x in self.supportedHeaders])
        self.setLine('')
        Headers.__init__(self, data)
        dataBegin = headerBegin + len(self)
        self.setData(data[dataBegin:])

    def isRequest(self):    return False
    def isResponse(self):   return True

    @classmethod
    def identify(self, data):
        data = data[:data.find(self.newline)]
        return len( data.split(self.newline) ) == 2


class SendMail(Message):

    def isRequest(self):    return True
    def isResponse(self):   return False

    @classmethod
    def identify(self, data):
        data = data[:data.find(self.newline)]
        # XXX TO DO

#------------------------------------------------------------------------------

class HTTPRequest(Request):
    supportedProtocols  = ( 'HTTP/1.1', 'HTTP/1.0' )

    supportedMethods    = (
        'OPTIONS',
        'GET',
        'HEAD',
        'POST',
        'PUT',
        'DELETE',
        'TRACE',
        'CONNECT',
        'LOCK',
        'MKCOL',
        'COPY',
        'MOVE',
    )

    supportedHeaders    = (
        'Accept',
        'Accept-Charset',
        'Accept-Encoding',
        'Accept-Language',
        'Accept-Ranges',
        'Age',
        'Allow',
        'Authorization',
        'Cache-Control',
        'Connection',
        'Content-Base',
        'Content-Encoding',
        'Content-Language',
        'Content-Length',
        'Content-Location',
        'Content-MD5',
        'Content-Range',
        'Content-Type',
        'Date',
        'ETag',
        'Expires',
        'From',
        'Host',
        'If-Match',
        'If-Modified-Since',
        'If-None-Match',
        'If-Range',
        'If-Unmodified-Since',
        'Last-Modified',
        'Location',
        'Max-Forwards',
        'Pragma',
        'Proxy-Authenticate',
        'Proxy-Authorization',
        'Public',
        'Range',
        'Referer',
        'Retry-After',
        'Server',
        'Transfer-Encoding',
        'Upgrade',
        'User-Agent',
        'Vary',
        'Via',
        'Warning',
    )

    def getURL(self):
        path   = self.getPath()
        pieces = list( urlsplit(path) )
        if pieces[0] == '':
            pieces[0] = 'http'
        if pieces[1] == '':
            if not self.has_key('Host'):
                raise Exception, "Can't get absolute URL"
            pieces[1] = self['Host'].split(self.value_separator)[0].strip()
        url = urlunsplit( tuple(pieces) )
        return url

    def setURL(self, url):
        pieces = urlsplit(url)
        if pieces[1] != '':
            self['Host'] = pieces[1]
##        pieces = ('', '') + pieces[2:]    # relative path
##        path   = urlunsplit(pieces)
##        self.setPath(path)
        self.setPath(url)                 # absolute path


class HTTPResponse(Response):
    supportedProtocols  = HTTPRequest.supportedProtocols
    supportedHeaders    = HTTPRequest.supportedHeaders

    supportedCodes      = {
        '100': 'Continue',
        '101': 'Switching Protocols',
        '200': 'OK',
        '201': 'Created',
        '202': 'Accepted',
        '203': 'Non-Authoritative Information',
        '204': 'No Content',
        '205': 'Reset Content',
        '206': 'Partial Content',
        '300': 'Multiple Choices',
        '301': 'Moved Permanently',
        '302': 'Moved Temporarily',
        '303': 'See Other',
        '304': 'Not Modified',
        '305': 'Use Proxy',
        '307': 'Temporary Redirect',
        '400': 'Bad Request',
        '401': 'Unauthorized',
        '402': 'Payment Required',
        '403': 'Forbidden',
        '404': 'Not Found',
        '405': 'Method Not Allowed',
        '406': 'Not Acceptable',
        '407': 'Proxy Authentication Required',
        '408': 'Request Timeout',
        '409': 'Conflict',
        '410': 'Gone',
        '411': 'Length Required',
        '412': 'Precondition Failed',
        '413': 'Request Entity Too Large',
        '414': 'Request-URI Too Long',
        '415': 'Unsupported Media Type',
        '500': 'Internal Server Error',
        '501': 'Not Implemented',
        '502': 'Bad Gateway',
        '503': 'Service Unavailable',
        '504': 'Gateway Timeout',
        '505': 'HTTP Version Not Supported'
    }

    errorPage = (
                        '<html>'
                        '<head><title>%(status)s %(text)s</title></head>'
                        '<body><h1>%(status)s</h1><h2>%(text)s</h2></body>'
                        '</html>'
                    )


HTTPRequest.makeResponse = HTTPResponse
HTTPResponse.makeRequest = HTTPRequest

#------------------------------------------------------------------------------

class RTSPRequest(Request):
    supportedProtocols  = ( 'RTSP/1.0' )

    supportedMethods    = (
        'OPTIONS',
        'DESCRIBE',
        'ANNOUNCE',
        'SETUP',
        'PLAY',
        'PAUSE',
        'TEARDOWN',
        'GET_PARAMETER',
        'SET_PARAMETER',
        'REDIRECT',
        'RECORD',
    )

    supportedHeaders    = (
        'Accept',
        'Accept-Encoding',
        'Accept-Language',
        'Allow',
        'Authorization',
        'Bandwidth',
        'Blocksize',
        'Cache-Control',
        'Conference',
        'Connection',
        'Content-Base',
        'Content-Encoding',
        'Content-Language',
        'Content-Length',
        'Content-Location',
        'Content-Type',
        'CSeq',
        'Date',
        'Expires',
        'From',
        'Host',
        'If-Match',
        'If-Modified-Since',
        'Last-Modified',
        'Location',
        'Proxy-Authenticate',
        'Proxy-Require',
        'Public',
        'Range',
        'Referer',
        'Retry-After',
        'Require',
        'RTP-Info',
        'Scale',
        'Speed',
        'Server',
        'Session',
        'Timestamp',
        'Transport',
        'Unsupported',
        'User-Agent',
        'Vary',
        'Via',
        'WWW-Authenticate',
    )


class RTSPResponse(Response):
    supportedProtocols  = RTSPRequest.supportedProtocols
    supportedHeaders    = RTSPRequest.supportedHeaders

    supportedCodes        = HTTPResponse.supportedCodes
    supportedCodes['250'] = 'Low on Storage Space'
    supportedCodes['405'] = 'Method Not Allowed'
    supportedCodes['451'] = 'Parameter Not Understood'
    supportedCodes['452'] = 'Conference Not Found'
    supportedCodes['453'] = 'Not Enough Bandwidth'
    supportedCodes['454'] = 'Session Not Found'
    supportedCodes['455'] = 'Method Not Valid in This State'
    supportedCodes['456'] = 'Header Field Not Valid for Resource'
    supportedCodes['457'] = 'Invalid Range'
    supportedCodes['458'] = 'Parameter Is Read-Only'
    supportedCodes['459'] = 'Aggregate Operation Not Allowed'
    supportedCodes['460'] = 'Only Aggregate Operation Allowed'
    supportedCodes['461'] = 'Unsupported Transport'
    supportedCodes['462'] = 'Destination Unreachable'
    supportedCodes['505'] = 'RTSP Version Not Supported'
    supportedCodes['551'] = 'Option not supported'


RTSPRequest.makeResponse = RTSPResponse
RTSPResponse.makeRequest = RTSPRequest

#------------------------------------------------------------------------------

# Session description
#         v=  (protocol version)
#         o=  (owner/creator and session identifier).
#         s=  (session name)
#         i=* (session information)
#         u=* (URI of description)
#         e=* (email address)
#         p=* (phone number)
#         c=* (connection information - not required if included in all media)
#         b=* (bandwidth information)
#         One or more time descriptions (see below)
#         z=* (time zone adjustments)
#         k=* (encryption key)
#         a=* (zero or more session attribute lines)
#         Zero or more media descriptions (see below)
#
# Time description
#         t=  (time the session is active)
#         r=* (zero or more repeat times)
#
# Media description
#         m=  (media name and transport address)
#         i=* (media title)
#         c=* (connection information - optional if included at session-level)
#         b=* (bandwidth information)
#         k=* (encryption key)
#         a=* (zero or more media attribute lines)
#
class SDPSession(Headers):
    header_separator    = '='
    header_fmt          = '%(name)s%(separator)s%(value)s'

    supportedHeaders    = 'vosiuepcbtrkam'

    def is_last_header(self, line):
        return self.count() > 0 and line.strip().startswith('v=')

    def is_multi_line_header(self, line):
        return False

    def getProtocol(self):      return self['v']
    def getOwner(self):         return self['o']
    def getSessionName(self):   return self['s']

    def setProtocol(self, protocol):    self['v'] = protocol
    def setOwner(self, owner):          self['o'] = owner
    def setName(self, name):            self['s'] = name

    def validate(self):
        return (
                self[0:0][0] == 'v' and
                Headers.validate(self)
                )

    @classmethod
    def identify(self, data):
        data = data[:data.find(self.newline)]
        return data.endswith('v=')

#------------------------------------------------------------------------------

class Factory:
    registeredParsers = tuple()

    @classmethod
    def getParser(self, data):
        for parserClass in self.registeredParsers:
            if parserClass.identify(data):
                return parserClass

    @classmethod
    def parse(self, data):
        parserClass = self.getParser(data)
        if parserClass is None:
            raise Exception, 'No suitable parser was found'
        return parserClass(data)

class ParserFactory(Factory):
    registeredParsers = (
        HTTPRequest,
        HTTPResponse,
        RTSPRequest,
        RTSPResponse,
        SDPSession,
        SendMail,
        ReadMail,
    )

class RequestFactory(Factory):
    registeredParsers = (
        HTTPRequest,
        RTSPRequest,
    )

class ResponseFactory(Factory):
    registeredParsers = (
        HTTPResponse,
        RTSPResponse,
    )

#------------------------------------------------------------------------------

def testme():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1',80))
    s.listen(1)
    print '-' * 79
    while 1:
        a, p = s.accept()
        d = ''
        while (Headers.newline*2) not in d:
            d += a.recv(0x1000)
##        x = HTTPRequest(d)
        c = RequestFactory.getParser(d)
        x = c(d)
        t = str(x)
        print t,
        print '-' * 79
##        r = HTTPResponse()
        r = c.makeResponse()
        r.setProtocol(x.getProtocol())
        r.setStatus('200')
        r.setText(r.supportedCodes['200'])
        r['Content-Length'] = len(t)
        r['Content-Type']   = 'text/plain'
        r['Connection']     = 'close'
        r.setData(t)
        w = str(r)
        print w,
        print '-' * 79
        a.sendall(w)
        a.close()

if __name__ == '__main__':
    testme()
