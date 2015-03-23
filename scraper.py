# -*- coding: utf8 -*-
import tidylib
import bs4
import requests
import arrow
import re
import sys
import codecs
import dateutil.parser
import datetime
import pytz
import time


class Scraper(object):
    def __init__(self):
        reload(sys)
        sys.setdefaultencoding('UTF-8')
        self._stockholm = pytz.timezone('Europe/Stockholm')

        tidylib.BASE_OPTIONS['bare'] = 1
        tidylib.BASE_OPTIONS['clean'] = 1
        tidylib.BASE_OPTIONS['drop-empty-paras'] = 1
        tidylib.BASE_OPTIONS['drop-font-tags'] = 1
        tidylib.BASE_OPTIONS['drop-proprietary-attributes'] = 1
        tidylib.BASE_OPTIONS['enclose-block-text'] = 1
        tidylib.BASE_OPTIONS['escape-cdata'] = 1
        tidylib.BASE_OPTIONS['hide-comments'] = 1
        tidylib.BASE_OPTIONS['logical-emphasis'] = 1
        tidylib.BASE_OPTIONS['output-xhtml'] = 1
        tidylib.BASE_OPTIONS['quote-nbsp'] = 1
        tidylib.BASE_OPTIONS['replace-color'] = 1
        tidylib.BASE_OPTIONS['uppercase-tags'] = 1
        tidylib.BASE_OPTIONS['break-before-br'] = 1
        tidylib.BASE_OPTIONS['indent'] = 1
        tidylib.BASE_OPTIONS['indent-attributes'] = 1
        tidylib.BASE_OPTIONS['indent-spaces'] = 1
        tidylib.BASE_OPTIONS['markup'] = 1
        tidylib.BASE_OPTIONS['punctuation-wrap'] = 1
        tidylib.BASE_OPTIONS['tab-size'] = 4
        tidylib.BASE_OPTIONS['vertical-space'] = 1
        tidylib.BASE_OPTIONS['wrap'] = 80
        tidylib.BASE_OPTIONS['wrap-script-literals'] = 1
        tidylib.BASE_OPTIONS['char-encoding'] = 'latin1'

        self._urlbase = 'http://sok.aftonbladet.se/?sortBy=pubDate&q='
        self._articles = {}

    def _search_keyword(self, keyword, before, after):
        r = requests.get(self._urlbase + keyword)
        html = r.text
        soup = bs4.BeautifulSoup(html)
        pretty = soup.prettify()
        soup = bs4.BeautifulSoup(pretty)

        ol = soup.find('ol', {'id': 'searchResultList'})
        articles = ''

        items = ol.find_all('li')

        # Prepare for later version where there can be multiple keywords.
        # One idea is to use the URL as the key in a dict, so multiple
        # hits can be found. If a hit is found, only the current keyword
        # needs to be added.

        for li in items:
            item = {}

            link = li.find('a')
            spans = li.find_all('span')
            category = spans[0]
            is_article = 'resultInfo' == category.get('class')[0]

            if is_article:
                timestamps = spans[1]
                created, updated = self._get_created_updated(timestamps.text)
                if created >= after and created < before:
                    title = link.contents[0].encode('utf-8').strip()
                    url = link.get('href').strip()
                    # FIXME keywords from dict
                    keywords = keyword
                    articles += self._get_article(url, title, created, updated, keywords)
        article_text, errors = tidylib.tidy_document(articles)
        return article_text


    def search_keywords(self, keywords, before, after):
        report = ''
        for keyword in keywords:
            report += self._search_keyword(keyword.strip(), before, after)

        return report

    def _parsedate(self, s):
        d = dateutil.parser.parse(s, fuzzy=True)
        if None == d.tzinfo:
            d = d.replace(tzinfo = self._stockholm)
        return d

    def _get_created_updated(self, datestr):
        datestr = datestr.strip()
        pos = datestr.find('(uppdaterad')

        if pos < 0 or ')' != datestr[-1]:
        	return 0, 0

        s1 = datestr[0:pos].strip()
        s2 = datestr[pos:].strip()
        created = self._parsedate(s1)
        updated = self._parsedate(s2)

        return created, updated

    def _tostring(self, resultset):
        s = u''
        for r in resultset:
            s += str(r)
        return s

    def _dstr(self, d):
        return d.strftime('%Y-%m-%d kl %H:%M')

    def _get_article(self, url, title, created, updated, keywords):
        r = requests.get(url)
        soup = bs4.BeautifulSoup(r.text)
        lead = soup.find('div', {'class': 'abLeadText'})
        body = soup.find_all('div', {'class': 'abBodyText'})
        address = soup.find('address')

        return \
            '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />' + \
            '<head>' + \
            '<title>' + title + '</title>' + \
            '</head>' + \
            '<body>' + \
            '<table CELLPADDING=6 RULES=GROUPS  FRAME=BOX>' + \
            '<tr>' + \
            '<td>Titel:</td>' + \
            '<td>' + title + '</td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Skapad:</td>' + \
            '<td>' + self._dstr(created) + '</td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Senast uppdaterad:</td>' + \
            '<td>' + self._dstr(updated) + '</td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Källa:</td>' + \
            '<td><i>' + url + '</i></td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Hämtad:</td>' + \
            '<td>' + self._dstr(datetime.datetime.now(self._stockholm)) + ' </td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Nyckelord:</td>' + \
            '<td>' + keywords + ' </td>' + \
            '</table>' + \
            self._tostring(lead) + \
            self._tostring(body) + \
            self._tostring(address) + \
            '<p style="page-break-before: always">'

