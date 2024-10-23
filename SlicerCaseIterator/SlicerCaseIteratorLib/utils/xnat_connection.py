from __future__ import absolute_import
from __future__ import unicode_literals
import datetime
import getpass
import hashlib
import logging
import platform
import re
import time

import requests
from six.moves.urllib import parse

from xnat import build_model, check_auth_guest, check_auth, detect_redirection, exceptions, query_netrc, _create_jsession, _query_jsession, _wipe_jsession, __version__
from xnat.session import XNATSession
from xnat.utils import JSessionAuth

xnat_logger = logging.getLogger('SlicerCaseIterator.Iterator.utils.Xnat')
time_out_pattern = re.compile(r'^"(?P<ts>\d{13}),(?P<duration>\d+)')

def connect(server, user=None, password=None, verify=True, netrc_file=None, debug=False,
            extension_types=True, loglevel=None, logger=None, detect_redirect=True,
            no_parse_model=False, default_timeout=300, auth_provider=None, jsession=None):
    """
    Connect to a server and generate the correct classed based on the servers xnat.xsd
    This function returns an object that can be used as a context operator. It will call
    disconnect automatically when the context is left. If it is used as a function, then
    the user should call ``.disconnect()`` to destroy the session and temporary code file.

    :param str server: uri of the server to connect to (including http:// or https://)
    :param str user: username to use, leave empty to use netrc entry or anonymous login.
    :param str password: password to use with the username, leave empty when using netrc.
                         If a username is given and no password, there will be a prompt
                         on the console requesting the password.
    :param bool verify: verify the https certificates, if this is false the connection will
                        be encrypted with ssl, but the certificates are not checked. This is
                        potentially dangerous, but required for self-signed certificates.
    :param str netrc_file: alternative location to use for the netrc file (path pointing to
                           a file following the netrc syntax)
    :param bool debug: Set debug information printing on and print extra debug information.
                       This is meant for xnatpy developers and not for normal users. If you
                       want to debug your code using xnatpy, just set the loglevel to DEBUG
                       which will show you all requests being made, but spare you the
                       xnatpy internals.
    :param bool extension_types: Flag to indicate whether or not to build an object model for
                                 extension types added by plugins.
    :param str loglevel: Set the level of the logger to desired level
    :param logging.Logger logger: A logger to reuse instead of creating an own logger
    :param bool detect_redirect: Try to detect a redirect (via a 302 response) and short-cut
                                 for subsequent requests
    :param bool no_parse_model: Create an XNAT connection without parsing the server data
                                model, this create a connection for which the simple
                                get/head/put/post/delete functions where, but anything
                                requiring the data model will file (e.g. any wrapped classes)
    :param int default_timeout: The default timeout of requests sent by xnatpy, is a 5 minutes
                                per default.
    :param str auth_provider: Set the auth provider to use to log in to XNAT.
    :return: XNAT session object
    :rtype: XNATSession

    Preferred use::

        >>> import xnat
        >>> with xnat.connect('https://central.xnat.org') as session:
        ...    subjects = session.projects['Sample_DICOM'].subjects
        ...    print('Subjects in the SampleDICOM project: {}'.format(subjects))
        Subjects in the SampleDICOM project: <XNATListing (CENTRAL_S01894, dcmtest1): <SubjectData CENTRAL_S01894>, (CENTRAL_S00461, PACE_HF_SUPINE): <SubjectData CENTRAL_S00461>>

    Alternative use::

        >>> import xnat
        >>> session = xnat.connect('https://central.xnat.org')
        >>> subjects = session.projects['Sample_DICOM'].subjects
        >>> print('Subjects in the SampleDICOM project: {}'.format(subjects))
        Subjects in the SampleDICOM project: <XNATListing (CENTRAL_S01894, dcmtest1): <SubjectData CENTRAL_S01894>, (CENTRAL_S00461, PACE_HF_SUPINE): <SubjectData CENTRAL_S00461>>
        >>> session.disconnect()
    """

    # Generate a hash for the connection
    hasher = hashlib.md5()
    hasher.update(server.encode('utf-8'))
    hasher.update(str(time.time()).encode('utf-8'))
    connection_id = hasher.hexdigest()

    # Setup the logger for this connection
    if logger is None:
        logger = logging.getLogger('xnat-{}'.format(connection_id))
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # create formatter
        if debug:
            formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(module)s:%(lineno)d >> %(message)s')
        else:
            formatter = logging.Formatter('[%(levelname)s] %(message)s')
        handler.setFormatter(formatter)

        if loglevel is not None:
            logger.setLevel(loglevel)
        elif debug:
            logger.setLevel('DEBUG')
        else:
            logger.setLevel('WARNING')

    # If verify is False, disable urllib3 warning and give a one time warning!
    if not verify:
        logger.warning('Verify is disabled, this will NOT verify the certificate of SSL connections!')
        logger.warning('Warnings about invalid certificates will be HIDDEN to avoid spam, but this')
        logger.warning('means that your connection can be potentially unsafe!')
        requests.packages.urllib3.disable_warnings()

    # Create the correct requests session
    requests_session = requests.Session()
    user_agent = "xnatpy/{version} ({platform}/{release}; python/{python}; requests/{requests})".format(
        version=__version__,
        platform=platform.system(),
        release=platform.release(),
        python=platform.python_version(),
        requests=requests.__version__
    )

    requests_session.headers.update({'User-Agent': user_agent})

    if not verify:
        requests_session.verify = False

    # Start out with any accidental auth, fill token once retrieved
    requests_session.auth = JSessionAuth()

    # Remove port and add .local to the domain in case there is no . in host
    # See issue #5388 in psf/requests for more info
    domain = parse.urlparse(server).netloc
    if ":" in domain:
        domain = domain.split(":")[0]
    if "." not in domain:
        domain = "{domain}.local".format(domain=domain)

    if jsession is not None:
        cookie = requests.cookies.create_cookie(
            domain=domain,
            name='JSESSIONID',
            value=jsession,
        )
        requests_session.cookies.set_cookie(cookie)
    else:
        if user is None and password is None:
            user, password = query_netrc(server, netrc_file, logger)

        if user is not None and password is None:
            password = getpass.getpass(prompt=str("Please enter the password for user '{}':".format(user)))

    # Check for redirects
    original_uri = server
    redirect_check_response = requests_session.get(server)

    if detect_redirect:
        server = detect_redirection(redirect_check_response, server, logger)

    if jsession is None:
        # If no username and password is found yet, re-query netrc after redirection
        if user is None and password is None:
            user, password = query_netrc(server, netrc_file, logger)


        if user is not None:
            # Get JSESSIONID and remove auth info again
            jsession_token = _create_jsession(requests_session,
                                              server=server,
                                              user=user,
                                              password=password,
                                              provider=auth_provider,
                                              debug=debug)
        else:
            _query_jsession(requests_session,
                            server=server,
                            debug=debug)
            jsession_token = None

        logger.debug("Retrieved JSESSION_TOKEN: {}".format(jsession_token))
        logger.debug("Requests session cookies: {}".format(requests_session.cookies))
    else:
        logger.debug("Set JSESSION_TOKEN to: {}".format(jsession))
        if requests_session.cookies.get('JSESSIONID', domain=domain) != jsession:
            message = 'Failed to login by re-using existing jsession, the session is probably close on the server!'
            logger.error(message)
            raise exceptions.XNATLoginFailedError(message)
        jsession_token = jsession

    # Set JSESSION token for rest of requests
    requests_session.auth = JSessionAuth(jsession_token)

    # Use a try so that errors result in closing the JSESSION and requests session
    try:
        # Check if login is successful
        if user is None and jsession is None:
            logged_in_user = check_auth_guest(requests_session, server=server, logger=logger)
        else:
            logger.debug('Checking login for {}, jsession argument {}'.format(user, jsession))
            logged_in_user = check_auth(requests_session, server=server, user=user, logger=logger)

        if jsession and logged_in_user == 'guest':
            logger.warning('Attempt to log in with jsession resulted in being logged in as'
                           ' "guest", something might have gone wrong')

        # Create the XNAT connection
        xnat_session = XNATSession(server=server, logger=logger,
                                   interface=requests_session, debug=debug,
                                   original_uri=original_uri, logged_in_user=logged_in_user,
                                   default_timeout=default_timeout, jsession=jsession_token, keepalive=False)

        # Parse data model and create classes
        if not no_parse_model:
            build_model(xnat_session, extension_types=extension_types, connection_id=connection_id)

        return xnat_session
    except:
        _wipe_jsession(requests_session, server)
        raise


def refresh_connection(xnat_session):
    global time_out_pattern, xnat_logger
    valid = True

    server_uri = xnat_session._original_uri
    time_out_match = time_out_pattern.search(xnat_session.interface.cookies.get('SESSION_EXPIRATION_TIME', ''))
    if time_out_match is not None:
        gd = time_out_match.groupdict()
        ts = int(gd['ts'])
        duration = int(gd['duration'])
        if int(datetime.datetime.now().timestamp() * 1000) > ts + duration:
            xnat_session.logger.debug('JSESSION token from interface expired, creating new token')
            valid = False
    else:
        xnat_logger.debug('No valid SESSION_EXPIRATION_TIME cookie found in interface')

    if valid:
        response = xnat_session.interface.get(server_uri + '/data/JSESSION', timeout=10)
        if response.status_code == 200:
            xnat_session.logger.debug('Refreshed JSESSION token')
            jsess = response.text
            xnat_session.interface.auth = JSessionAuth(jsess)

            time_out_match = time_out_pattern.search(response.cookies.get('SESSION_EXPIRATION_TIME', ''))
            if time_out_match is not None:
                gd = time_out_match.groupdict()
                ts = int(gd['ts'])
                duration = int(gd['duration'])
                if int(datetime.datetime.now().timestamp() * 1000) > ts + duration:
                    xnat_session.logger.warning('JSESSION token expired, creating new token')
                    valid = False
            else:
                xnat_logger.debug('No valid SESSION_EXPIRATION_TIME cookie found')
        elif response.status_code == 401:
            xnat_session.logger.debug('JSESSION authentication failed, creating new token')
            valid = False
        else:
            xnat_session.logger.debug('JSESSION refresh returned status code %i!', response.status_code)
            valid = False

    if not valid:
        # refresh token!
        user, password = query_netrc(server_uri, None, xnat_session.logger)
        if user is None:
            user, password = query_netrc(parse.urlunparse(xnat_session._server), None, xnat_session.logger)
        if 'JSESSIONID' in xnat_session.interface.cookies:
            del xnat_session.interface.cookies['JSESSIONID']
        response = xnat_session.interface.get(server_uri + '/data/JSESSION', timeout=10, auth=(user, password))
        jsess = response.text
        xnat_session.interface.auth = JSessionAuth(jsess)
