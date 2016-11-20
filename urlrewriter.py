#!/usr/bin/env python
# -*- coding: utf-8 -*-


# Only tested on Python 2.7.  Might not run on Python 3.x.

import praw
import re
import codecs
import sys
import os
import urlparse
import urllib2
import praw_script_oauth

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

UserAgent = 'URLRewriter'
ScraperUserAgent = 'a Mozilla/5.0 incompatible agent'
SubmissionLimit = 100

Footer = u"***\n^^code ^^in [^^github](https://github.com/site2000/urlrewriter/)"

class URLRewrite:
    def __init__(self, mr):
        self._match = mr[0]
        self._check = mr[1]
        self._repl = mr[2]
        self._desc = mr[3]

    def match(self, url):
        return re.match(self._match, url)

    def check(self, url, title=''):
        if self._check:
            return self._check(url, title)
        else:
            return True

    def sub(self, mo, title):
        return self._repl(mo, title)

    def description(self):
        return self._desc

def _sankei_next_check(url, title):
    try:
        rsp = urllib2.urlopen(url)
    except urllib2.URLError, e:
        print url.encode('utf_8') + ': ' + e.reason
        return False
    text = rsp.read().lower()
    rsp.close()
    return '<link rel="next"' in text

def _ism_next_check(url, title):
    try:
        rsp = urllib2.urlopen(url)
    except urllib2.URLError, e:
        print url.encode('utf_8') + ': ' + e.reason
        return False
    text = rsp.read().lower()
    rsp.close()
    return \
        '<div id="multipage"' in text or \
        '<span class="pagination">' in text or \
        '<div class="article-pagination">' in text

def _reuters_next_check(url, title):
    if re.match('.+sp=true$', url):
        return False
    try:
        rsp = urllib2.urlopen(url)
    except urllib2.URLError, e:
        print url.encode('utf_8') + ': ' + e.reason
        return False
    text = rsp.read().lower()
    rsp.close()
    return '<a id="singlepagelink"' in text

def _mainichi_yahoo_rewriter(url, title):
    # The type of Submission.title is unicode, not str.
    reqhdr = {'User-Agent': ScraperUserAgent}
    req = urllib2.Request(url, headers=reqhdr)
    try:
        rsp = urllib2.urlopen(req)
    except urllib2.URLError, e:
        print url.encode('utf_8') + ': ' + e.reason
        return None
    text = rsp.read()
    rsp.close()
    m = re.search('<title>(.+)</title>', text)
    if m is None:
        t = title
    else:
        # articles without registration, no need to rewrite
        return None
        #td = m.group(1).decode('utf_8')
        #if re.match(u'会員登録のお願い', td):
        #    t = title
        #else:
        #    t = td

    t = re.sub(u' - 毎日新聞', '', t)
    m = re.match(u'(.+?)：(.+)', t)
    if m is None:
        y_title = t
    else:
        y_title = u'＜' + m.group(1) + u'＞' + m.group(2)
    srch_url = 'http://news.search.yahoo.co.jp/search?p=' + \
               urllib2.quote(y_title.encode('utf_8')) + \
               u'&ei=UTF-8&fr=news_sw'
    req = urllib2.Request(srch_url, headers=reqhdr)
    try:
        rsp = urllib2.urlopen(req)
    except urllib2.URLError, e:
        print url.encode('utf_8') + ': ' + e.reason
        return None
    srch_text = rsp.read()
    rsp.close()
    for yurl in re.findall('<a href="(http://headlines.yahoo.co.jp/hl.+?)"',
                           srch_text):
        req = urllib2.Request(yurl, headers=reqhdr)
        try:
            rsp = urllib2.urlopen(req)
        except urllib2.URLError, e:
            print url.encode('utf_8') + ': ' + e.reason
            return None
        text = rsp.read()
        rsp.close()
        if ('<title>' + y_title.split(' ')[0]) in text.decode('utf_8'):
            print url + ' -> ' + yurl
            return yurl
    return None

# need new-style class for property
class RewritableURL(object):
    rewriters = map(
        URLRewrite,
        [
            # The print pages of toyokeizai.net seem to check referer.
            # Can not open them directly.
            ['(https?://)(diamond\.jp|gendai\.ismedia\.jp)/articles/-/([\d]+)',
             _ism_next_check,
             lambda mo, t: mo.group(1) + mo.group(2) + "/articles/print/" + mo.group(3),
             u'1ページで表示(プリンタ向けページ使用)'],
            # sankei does not setup SSL correctly.
            ['(http)://www.sankei.com/(.+?)/news/(.+)-n\d.html',
             _sankei_next_check,
             lambda mo, t: mo.group(1) + '://www.sankei.com/' + mo.group(2) + '/print/' + mo.group(3) + '-c.html',
             u'1ページで表示(プリンタ向けページ使用)'],
            #['(https?)://www.sankei.com/(.+?)/news/(.+)-n\d.html',
            # _sankei_next_check,
            # lambda mo, t: mo.group(1) + '://www.sankei.com/' + mo.group(2) + '/print/' + mo.group(3) + '-c.html',
            # u'1ページで表示(プリンタ向けページ使用)'],
            ['(https?)://jp.reuters.com/article/(.+)',
             _reuters_next_check,
             lambda mo, t: mo.group(1) + '://jp.reuters.com/article/' + mo.group(2) + '?sp=true',
             u'1ページで表示'],
                         
            ['(https?)://www.dailyshincho.jp/article/(.+/)(?!\?all=1)$',
             None,
             lambda mo, t: mo.group(1) + '://www.dailyshincho.jp/article/' + mo.group(2) + '?all=1',
             u'全て読む'],
            ['https://m.reddit.com/(.+)',
             None,
             lambda mo, t: "https://www.reddit.com/" + mo.group(1),
             u'PC向けURL'],
            ['(https?)://jp.mobile.reuters.com/(.+)',
             None,
             lambda mo, t: mo.group(1) + "://jp.reuters.com/" + mo.group(2) + '?sp=true',
             u'PC向けURL'],
            ['(https?)://sp.yomiuri.co.jp/(.+)',
             None,
             lambda mo, t: mo.group(1) + "://www.yomiuri.co.jp/" + mo.group(2),
             u'PC向けURL'],
            ['(https?)://news.tbs.co.jp/sp/(.+)',
             None,
             lambda mo, t: mo.group(1) + "://news.tbs.co.jp/" + mo.group(2),
             u'PC向けURL'],
            ['https?://mainichi.jp/.*articles/.+',
             None,
             lambda mo, t: _mainichi_yahoo_rewriter(mo.group(0), t),
             u'Yahooニュースへの配信版'],
        ])

    def __init__(self, url, title):
        self.url = url
        self.title = title
        self._rewritten_url = None
        self._is_rewritable = None
        self._rewriter = None

    def _rewrite(self):
        if self._is_rewritable is None:
            for ur in RewritableURL.rewriters:
                m = ur.match(self.url)
                if m:
                    if ur.check(self.url, self.title):
                        self._rewritten_url = ur.sub(m, self.title)
                        break
            self._is_rewritable = not (self._rewritten_url is None)
            if self._is_rewritable:
                self._rewriter = ur.description()
                req = urllib2.Request(self._rewritten_url,
                                      headers={'User-Agent': ScraperUserAgent})
                try:
                    rsp = urllib2.urlopen(req)
                    rsp.close()
                except URLError, e:
                    print url.encode('utf_8') + ': ' + e.reason
                    self._rewritten_url = None
                    self._is_rewritable = False
                    self._rewriter = None

    @property
    def rewritten_url(self):
        if self._is_rewritable is None:
            self._rewrite()
        return self._rewritten_url

    @property
    def rewriter(self):
        return self._rewriter

# need new-style class for property
class AppConfig(object):
    def __init__(self):
        self.config = configparser.ConfigParser()

        self._last_id = ''
        self._last_date = 0.0
        self._subreddit = ''

        if 'APPDATA' in os.environ:
            dir = os.environ['APPDATA']
        elif 'XDG_CONFIG_HOME' in os.environ:
            dir = os.environ['XDG_CONFIG_HOME']
        else:
            dir = '.'

        self.config_path = "%s/urlrewriter.ini" % dir
        self.config.read(self.config_path)

        try:
            self._subreddit = self.config.get(configparser.DEFAULTSECT, 'subreddit')
        except configparser.NoOptionError:
            self._subreddit = 'test'

        try:
            self._last_id = self.config.get(configparser.DEFAULTSECT, 'last_id')
            self._last_date = float(self.config.get(configparser.DEFAULTSECT, 'last_date'))
        except configparser.NoOptionError:
            self._last_id = ''
            self._last_date = 0.0

    def write(self):
        with open(self.config_path, 'wb') as configfile:
            self.config.write(configfile)

    @property
    def subreddit(self):
        return self._subreddit
    
    @property
    def last_id(self):
        return self._last_id
    
    @last_id.setter
    def last_id(self, value):
        self._last_id = value
        self.config.set(configparser.DEFAULTSECT, 'last_id', value)

    @property
    def last_date(self):
        return self._last_date
    
    @last_date.setter
    def last_date(self, value):
        self._last_date = value
        self.config.set(configparser.DEFAULTSECT, 'last_date', value)

#######################################################################

def rewrite_info_message(url, title=''):
    #print "Checking for " + url.encode('utf_8')
    reurl = RewritableURL(url, title)
    s = reurl.rewritten_url
    if s is not None:
        return reurl.rewriter + u":  \n" + s + u"\n\n"
    else:
        return u''

def main():
    appconfig = AppConfig()

    reddit = praw.Reddit(UserAgent)

    oauth_token = praw_script_oauth.get_oauth_token(
        reddit.config.client_id,
        reddit.config.client_secret,
        reddit.config.user,
        reddit.config.pswd,
        UserAgent)
    reddit.set_oauth_app_info(
        reddit.config.client_id,
        reddit.config.client_secret,
        'http://unused.example.com/')
    reddit.set_access_credentials('*', oauth_token)
    reddit.config.api_request_delay = 1

    #print 'Authenicated as ' + str(reddit.get_me())

    subr = reddit.get_subreddit(appconfig.subreddit)

    this_last_date = 0.0
    this_last_id = ''
    n_rwt = n_cap = n_new = 0
    last_id = appconfig.last_id
    last_date = appconfig.last_date
    for subm in subr.get_new(limit = SubmissionLimit):
        if this_last_date == 0.0:
            this_last_date = subm.created_utc
            this_last_id = subm.id

        if subm.created_utc < last_date or subm.id == last_id:
            break

        n_new += 1
        text = u''
        if subm.is_self:
            if subm.selftext_html:
                for url in re.findall('<a href="(https?://[^\s>]+)">',
                                      subm.selftext_html):
                    text += rewrite_info_message(url)
        else:
            text = rewrite_info_message(subm.url, subm.title)

        if text != u'':
            print text.encode('utf_8')
            # Avoid double comments on a submission by updating the last run record.
            # The checks for older submissions will be dropped but it is ok since
            # this program is not expected to run perfectly...
            if n_rwt == 0:
                appconfig.last_id = this_last_id
                appconfig.last_date = this_last_date
                appconfig.write()

            try:
                subm.add_comment((text + Footer).encode('utf_8'))
            except praw.errors.InvalidCaptcha, e:
                n_cap += 1
                break
            n_rwt += 1

    if n_new > 0:
        print "Processed %d, rewritten %d, captcha-ed %d" % (n_new, n_rwt, n_cap)

    appconfig.last_id = this_last_id
    appconfig.last_date = this_last_date
    appconfig.write()

if __name__ == '__main__':
    main()
