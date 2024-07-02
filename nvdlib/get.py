import requests
import time
import logging

from json.decoder import JSONDecodeError

logger = logging.getLogger(__name__)

def __get(product, headers, parameters, limit, verbose, delay):
    """Calculate required pages for multiple requests, send the GET request with the search criteria, return list of CVEs or CPEs objects."""

    # Get the default 2000 items to see the totalResults and determine pages required.
    if product == 'cve':
        link = 'https://services.nvd.nist.gov/rest/json/cves/2.0?'
    elif product == 'cpe':
        link = 'https://services.nvd.nist.gov/rest/json/cpes/2.0?'
    elif product == 'cpeMatch':
        link = 'https://services.nvd.nist.gov/rest/json/cpematch/2.0?'

    # Requests doesn't really work with dictionary parameters that have no value like `isVulnerable`. The workaround is to just pass a string instead.
    # This joins the parameters into a string with '&' and if a key contains a value then it will join the values with '='
    stringParams = '&'.join(
        [k if v is None else f"{k}={v}" for k, v in parameters.items()])
    if verbose:
        logger.debug('Filter:\n' + link + stringParams)

    raw = requests.get(link, params=stringParams, headers=headers, timeout=30)
    raw.encoding = 'utf-8'
    raw.raise_for_status()

    try:  # Try to convert the request to JSON. If it is not JSON, then print the response and exit.
        raw = raw.json()
        if 'message' in raw:
            raise LookupError(raw['message'])
    except JSONDecodeError:
        logger.debug('Invalid search criteria syntax: ' + str(raw))
        logger.debug('Attempted search criteria: ' + str(parameters))

    if not delay:
        delay = 6
    time.sleep(delay)

    # If a limit is in the search criteria or the total number of results are less than or equal to the default 2000 that were just requested, return and don't request anymore.
    totalResults = raw['totalResults']
    if limit or totalResults <= 2000:
        return raw

    # If the results is more than the API limit, figure out how many pages there are and calculate the number of requests.
    # Use the page we already grabbed, then send a request starting at startIndex = 2000, then get the next page and ask for 2000 more results at the 2000th index result until all results have been grabbed.
    # Add each ['vulnerabilities'] or ['products'] list from each page to the end of the first request. Effectively creates one data point.
    elif totalResults > 2000:
        pages = (totalResults // 2000)
        startIndex = 2000
        if product == 'cve':
            path = 'vulnerabilities'
        else:
            path = 'products'

        rawTemp = raw[path]

        for eachPage in range(pages):
            parameters['resultsPerPage'] = '2000'
            parameters['startIndex'] = str(startIndex)
            stringParams = '&'.join(
                [k if v is None else f"{k}={v}" for k, v in parameters.items()])
            if verbose:
                logger.debug('Filter:\n' + link + stringParams)
            try:
                getReq = requests.get(
                    link, params=stringParams, headers=headers, timeout=30)
                getReq.encoding = 'utf-8'
                getData = getReq.json()[path]
                time.sleep(delay)
            except JSONDecodeError:
                logger.debug('JSONDecodeError')
                logger.debug('Something went wrong: ' + str(getReq))
                logger.debug('Attempted search criteria: ' + str(stringParams))
                logger.debug('URL: ' + getReq.request.url)
                getReq.raise_for_status()
            rawTemp.extend(getData)
            startIndex += 2000
        raw[path] = rawTemp
        return raw


def __get_with_generator(product, headers, parameters, limit,
                         verbose, delay, max_delay=30):
    # Get the default 2000 items to see the totalResults and determine pages required.
    if product == 'cve':
        link = 'https://services.nvd.nist.gov/rest/json/cves/2.0?'
    elif product == 'cpe':
        link = 'https://services.nvd.nist.gov/rest/json/cpes/2.0?'
    elif product == 'cpeMatch':
        link = 'https://services.nvd.nist.gov/rest/json/cpes/2.0?'
    startIndex = 0
    while True:
        stringParams = '&'.join(
            [k if v is None else f"{k}={v}" for k, v in parameters.items()])
        if verbose:
            logger.debug('Filter:\n' + link + stringParams)
        rate_delay = 6
        while True:
            if rate_delay > max_delay:
                rate_delay = max_delay

            try:
                raw = requests.get(link, params=stringParams,
                                   headers=headers, timeout=30)
                if raw.status_code == 403:
                    logger.debug(f'Request returned a rate limit error. Retrying in {rate_delay} seconds...')
                    time.sleep(rate_delay)
                    rate_delay *= 2
                if str(raw.status_code).startswith('5'):
                    logger.debug(f'Request failed. Retrying in {rate_delay} seconds...')
                    time.sleep(rate_delay)
                    rate_delay *= 2
                else:
                    break
            except requests.exceptions.ReadTimeout:
                logger.debug(f'Request failed. Retrying in {rate_delay} seconds...')
                time.sleep(rate_delay)
                rate_delay *= 2
            except requests.exceptions.ConnectionError:
                logger.debug(f'Connection failed. Retrying in {rate_delay} seconds...')
                time.sleep(rate_delay)
                rate_delay *= 2

        raw.encoding = 'utf-8'
        raw.raise_for_status()

        try:  # Try to convert the request to JSON. If it is not JSON, then print the response and exit.
            raw = raw.json()
            if 'message' in raw:
                raise LookupError(raw['message'])
        except JSONDecodeError:
            logger.debug('Invalid search criteria syntax: ' + str(raw))
            logger.debug('Attempted search criteria: ' + str(parameters))
        yield raw

        totalResults = raw['totalResults']

        startIndex += 2000
        parameters['startIndex'] = str(startIndex)
        parameters['resultsPerPage'] = '2000'

        if verbose and startIndex == 0:
            if limit:
                logger.debug(f'Query returned {limit} total records')
            else:
                logger.debug(f'Query returned {totalResults} total records')

        if verbose and not limit:
            if startIndex < totalResults:
                logger.debug(
                    f'Getting {product} batch {raw["startIndex"]} to {startIndex}')
            else:
                logger.debug(
                    f'Getting {product} batch {raw["startIndex"]} to {totalResults}')

        if limit or startIndex > totalResults:
            break

        if not delay:
            delay = 6
        time.sleep(delay)
