#!/usr/bin/env python3

from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
from feedgen.feed import FeedGenerator
from xml.etree import ElementTree
from bs4 import BeautifulSoup
import pytz
import requests
import os.path
import os


CACHE_DIR = os.environ.get('CACHE_DIR')
if not CACHE_DIR:
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '_cache')

URL_BASE = os.environ.get('URL_BASE')
if not URL_BASE:
    URL_BASE = 'https://crgwbr.com/jworg-magazines'


class Article:
    def __init__(self, item):
        self.guid = item.find('guid').text
        self.title = item.find('title').text
        self.link = item.find('link').text
        self.description = item.find('description').text
        self.pub_date = parse_date(item.find('pubDate').text)

    @property
    def mid(self):
        if not hasattr(self, '_mid'):
            resp = requests.get(self.link)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content)
            body = soup.find('body')
            body_id = body.get('id')
            if body_id.startswith('mid'):
                self._mid = body_id.replace('mid', '')
            else:
                self._mid = None
        return self._mid

    @property
    def audio_file(self):
        if not hasattr(self, '_audio_file'):
            try:
                resp = requests.get('https://apps.jw.org/GETPUBMEDIALINKS', params={
                    'docid': self.mid,
                    'output': 'json',
                    'fileformat': 'MP3',
                    'alllangs': 0,
                    'track': 1,
                    'langwritten': 'E',
                    'txtCMSLang': 'E',
                })
                resp.raise_for_status()
                self._audio_file = resp.json().get('files', {}).get('E', {}).get('MP3', [None])[0]
            except requests.RequestException as e:
                self._audio_file = None
        return self._audio_file



def list_articles():
    resp = requests.get('https://www.jw.org/en/whats-new/rss/WhatsNewWebArticles/feed.xml')
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    for channel in root.findall('channel'):
        for item in channel.findall('item'):
            yield Article(item)



def main(output='whats-new.atom'):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.podcast.itunes_category('Religion & Spirituality', 'Christianity')
    fg.podcast.itunes_image("%s/icon.png" % URL_BASE)
    fg.title("JW.ORG - What's New")
    fg.description("See what has been recently added to jw.org, the official website of Jehovah's Witnesses.")
    fg.link(href="{}{}".format(URL_BASE, output), rel='self')

    for article in list_articles():
        print(article.title)
        audio_file = article.audio_file
        if audio_file:
            fe = fg.add_entry()
            fe.id(article.guid)
            fe.title(article.title)
            fe.description(article.description)
            fe.updated(article.pub_date)
            fe.published(article.pub_date)
            fe.enclosure(audio_file['file']['url'], str(audio_file['duration']), audio_file['mimetype'])
            fe.link(href=audio_file['file']['url'], type=audio_file['mimetype'])

    fg.rss_str(pretty=True)
    fg.rss_file(os.path.join(CACHE_DIR, output))



if __name__ == "__main__":
    main()
