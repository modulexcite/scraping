#!/usr/local/bin/python
# vim: set fileencoding=utf8 :
from __future__ import print_function
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
import cachecontrol
import html2text
import xlsxwriter



class Scraper(object):
    def __init__(self, grace=0, publication=''):
        self._publication = publication
        if publication == 'aftonbladet.se':
            self._search_keyword = self._search_keyword_aftonbladet
            self._urlbase = 'http://sok.aftonbladet.se/?sortBy=pubDate&q='
        elif publication == 'idg.se':
            self._search_keyword = self._search_keyword_idg
        else:
            raise ValueError('Publication "' +
                             publication +
                             '" not supported for scraping')

        self._proxies = {
            'http': 'http://127.0.0.1:3128'
        }
        self._publication = publication
        self._html2text = html2text.HTML2Text()
        self._html2text.ignore_links = True
        self._html2text.ignore_images = True
        self._html2text.body_width = 78
        self._html2text.images_to_alt = True

        self._grace = grace
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

        self._articles = {}
        self._keywords = {}
        sess = requests.session()
        self._cached_sess = cachecontrol.CacheControl(sess)

    def _search_keyword_aftonbladet(self, keyword, before, after):
        index = 0
        we_may_still_find_what_we_are_looking_for = True

        while we_may_still_find_what_we_are_looking_for:
            url = self._urlbase + keyword + '&start=' + str(index)
            print(url)
            try:
                r = self._cached_sess.get(
                    self._urlbase +
                    keyword +
                    '&start=' +
                    str(index),
                    proxies=self._proxies)
            except requests.exceptions.ConnectionError as e:
                print(e)
                time.sleep(60)
                break
            time.sleep(self._grace) # Sleep to not hammer the web server - be polite

            html = r.text
            soup = bs4.BeautifulSoup(html)
            pretty = soup.prettify()
            soup = bs4.BeautifulSoup(pretty)

            ol = soup.find('ol', {'id': 'searchResultList'})
            if ol is None:
                break

            items = ol.find_all('li')

            # By default try to give up:
            we_may_still_find_what_we_are_looking_for = False
            for li in items:
                item = {}

                link = li.find('a')
                spans = li.find_all('span')
                category = spans[0]
                is_article = 'resultInfo' == category.get('class')[0]

                if is_article:
                    # A search result! We may yet prevail!
                    we_may_still_find_what_we_are_looking_for = True
                    timestamps = spans[1]
                    created, updated = self._get_created_updated(timestamps.text)
                    if created < after:
                        # Alas, results are too old.
                        we_may_still_find_what_we_are_looking_for = False
                    if created >= after and created < before:
                        title = link.contents[0].encode('utf-8').strip()
                        url = link.get('href').strip()
                        self._get_article(url, title, created, updated, keyword)
                        # Step out of loop, so we can restart search on next index...
                        time.sleep(self._grace) # Sleep to not hammer the web server - be polite
                        break
            index += 1

    def _render_email(self, email):
        return '<a href="mailto:' + email + '">' + email + '</a>'


    def generate_report(self, keywords, before, after):
        # Gather data
        for keyword in keywords:
            self._search_keyword(keyword.strip(), before, after)

        # Build Excel report
        workbook = xlsxwriter.Workbook(self._publication + '.xlsx')
        fmt = workbook.add_format({'bold': True, 'font_name': 'Verdana'})
        sheet = workbook.add_worksheet('Data')
        col = 0
        for rowname in ['#',
                        'fetched',
                        'keywords',
                        'publication',
                        'date',
                        'updated',
                        'author',
                        'author_email',
                        'url',
                        'title',
                        'fulltext_plain']:
            sheet.write(0, col, rowname, fmt)
            col += 1

        # Build HTML report
        report = '''
<html>
 <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <head>
   <style>
    body {
      line-height: 1.0;
    }
   </style>
  </head>
  <body>
   Sökning på ''' + self._publication + ' från ' + \
    str(after.date()) + ' till ' + str(before.date()) + \
''', med nyckelord enligt tabellen:
   <table BORDER="1" RULES=ALL FRAME=VOID CELLPADDING="10">
    <tr>
     <th>Nyckelord</th>
     <th>Matchande länkar</th>
    </tr>
'''

        for keyword, props in self._keywords.items():
            report += \
                '<tr>' + \
                '<td><small>' + keyword + '</small></td>' + \
                '<td>'
            for url in props['url']:
                report += ' <small><a href="' + url + '">' + url + '</a></small> '
            report += \
                '</td>' + \
                '</tr>'

        report += \
            '</table>' + \
            '<p style="page-break-before: always" />'

        row = 1
        sheet.set_column(0, 0, 1)
        sheet.set_column(1, 1, 29)
        sheet.set_column(2, 2, 30)
        sheet.set_column(3, 3, 12)
        sheet.set_column(4, 4, 22)
        sheet.set_column(5, 5, 22)
        sheet.set_column(6, 6, 21)
        sheet.set_column(7, 7, 35)
        sheet.set_column(8, 8, 70)
        sheet.set_column(9, 9, 70)
        sheet.set_column(10, 10, 240)
        for _key, a in self._articles.items():
            keywords = ', '.join(a['keywords'])

            sheet.write(row,  0, row)
            sheet.write(row,  1, a['fetched'].isoformat())
            sheet.write(row,  2, keywords)
            sheet.write(row,  3, self._publication)
            sheet.write(row,  4, a['created'].isoformat())
            sheet.write(row,  5, a['updated'].isoformat())
            sheet.write(row,  6, self._html2text.handle(a['author']))
            sheet.write(row,  7, a['author_email'])
            sheet.write(row,  8, a['url'])
            sheet.write(row,  9, a['title'].replace('\n', ' '))
            sheet.write(row, 10, a['fulltext_plain'].replace('\n', ' '))

            report += \
            '<table CELLPADDING=6 RULES=GROUPS  FRAME=BOX>' + \
            '<tr>' + \
            '<td>Titel:</td>' + \
            '<td><b>' + a['title'] + '</b></td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Skapad:</td>' + \
            '<td>' + self._dstr(a['created']) + '</td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Senast uppdaterad:</td>' + \
            '<td>' + self._dstr(a['updated']) + '</td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Källa:</td>' + \
            '<td><i><a href="' + a['url'] + '">' + a['url'] + '</a></i></td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Hämtad:</td>' + \
            '<td>' + self._dstr(a['fetched']) + ' </td>' + \
            '</tr>' + \
            '<tr>' + \
            '<td>Nyckelord:</td>' + \
            '<td>' + keywords + ' </td>' + \
            '</table>' + \
            a['lead'] + \
            a['body'] + \
            a['author'] + \
            self._render_email(a['author_email']) + \
            '<p style="page-break-before: always" />'

            row += 1

        report += \
            '</body>' + \
            '</html>'

        report_text, errors = tidylib.tidy_document(report)

        workbook.close()

        return report_text

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
        if not resultset:
            return ''
        s = ''
        for r in resultset:
            s += str(r)
        return s

    def _dstr(self, d):
        return d.strftime('%Y-%m-%d kl %H:%M')

    def _extract_email_address(self, href):
        reobj = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,6}\b", re.IGNORECASE)
        l = re.findall(reobj, href)
        if l:
            return l[0]
        return ''

    def _get_article(self, url, title, created, updated, keyword):
        request_done = False
        while not request_done:
            try:
                r = self._cached_sess.get(url)
                request_done = True
            except requests.exceptions.ConnectionError as e:
                print(r)

        soup = bs4.BeautifulSoup(r.text)
        lead = soup.find('div', {'class': 'abLeadText'})
        body = soup.find_all('div', {'class': 'abBodyText'})
        author = ''
        email = ''

        author = soup.find('address')
        if author:
            anchor = author.find('a')
            if anchor and anchor.attrs.has_key('href'):
                email = self._extract_email_address(anchor['href'])
                author = self._html2text.handle(self._tostring(anchor)),

        if keyword not in self._keywords:
            self._keywords[keyword] = {'url': []}
        if url not in self._keywords[keyword]['url']:
            self._keywords[keyword]['url'].append(url)

        if url in self._articles:
            if keyword not in self._articles[url]['keywords']:
                self._articles[url]['keywords'].append(keyword)
        else:
            leadtext = self._tostring(lead)
            bodytext = self._tostring(body)
            fulltext = leadtext + bodytext
            self._articles[url] = {
                'title':          title,
                'created':        created,
                'updated':        updated,
                'url':            url,
                'fetched':        datetime.datetime.now(self._stockholm),
                'keywords':       [keyword],
                'lead':           '<small>' + self._tostring(lead) + '</small>',
                'body':           '<small>' + self._tostring(body) + '</small>',
                'author':         self._tostring(author),
                'author_email':   email,
                'publication':    'aftonbladet.se',
                'fulltext_plain': self._html2text.handle(fulltext),
            }

