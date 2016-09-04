#!/usr/bin/env python3

from datetime import datetime, timedelta
from feedgen.feed import FeedGenerator
from pydub import AudioSegment
import os
import os.path
import hashlib
import pytz
import re
import requests
import xml.etree.cElementTree as etree
import yaml


MNEMONICS = ('g', 'w', 'wp', )
LANGUAGES = ('E', )
FORMAT = 'mp3'

CACHE_DIR = os.path.join(os.path.dirname(__file__), '_cache')
MANIFEST = os.path.join(CACHE_DIR, '_manifest.yml')
URL_BASE = 'https://crgwbr.com/jworg-magazines'


class Manifest(object):
    def get_issue_hash(self, issue):
        manifest = self._load()
        return manifest.get(issue.lang, {}).get(issue.mnemonic, {}).get(issue.issue_date, {}).get('hash')

    def get_article_count(self, issue):
        manifest = self._load()
        return len( manifest.get(issue.lang, {}).get(issue.mnemonic, {}).get(issue.issue_date, {}).get('articles', []) )

    def save_issue(self, issue, audio):
        manifest = self._load()
        if issue.lang not in manifest:
            manifest[issue.lang] = {}
        if issue.mnemonic not in manifest[issue.lang]:
            manifest[issue.lang][issue.mnemonic] = {}
        manifest[issue.lang][issue.mnemonic][issue.issue_date] = {
            'hash': issue.hash,
            'created_on': datetime.now(),
            'file': issue.local,
            'duration': audio.duration_seconds,
            'title': issue.title,
            'articles': [a.local for a in issue.articles]
        }
        self._save(manifest)

    def prune(self):
        # Remove article files
        manifest = self._load()
        stale_threshold = datetime.now() - timedelta(days=150)
        for lang, mnemonics in manifest.items():
            for mnemonic, issues in mnemonics.items():
                stale_issues = []
                for issue, data in issues.items():
                    for f in data.get('articles', []):
                        try:
                            os.unlink(f)
                        except FileNotFoundError:
                            pass

                    if data['created_on'] <= stale_threshold:
                        stale_issues.append(issue)
                for issue in stale_issues:
                    print('Removing stale issue %s %s %s' % (lang, mnemonic, issue))
                    os.unlink( manifest[lang][mnemonic][issue]['file'] )
                    del manifest[lang][mnemonic][issue]
        self._save(manifest)


    def export_feed(self, output):
        fg = FeedGenerator()
        fg.load_extension('podcast')
        fg.podcast.itunes_category('Religion & Spirituality', 'Christianity')

        fg.title('jw.org Magazines')
        fg.description('Combined Feed of Watchtower (public), Watchtower (study), and Awake! in English from jw.org.')
        fg.link(href="%s/%s" % (URL_BASE, output), rel='self')

        manifest = self._load()
        entries = []
        for lang, mnemonics in manifest.items():
            for mnemonic, issues in mnemonics.items():
                for issue, data in issues.items():
                    entries.append((issue, data))

        for issue, entry in sorted(entries, key=lambda i: i[0], reverse=True):
            fe = fg.add_entry()

            fe.id( entry['hash'] )
            fe.title( entry['title'] )
            fe.description( entry['title'] )
            fe.published( pytz.utc.localize( entry['created_on'] ) )
            url = "%s/%s" % (URL_BASE, os.path.basename(entry['file']))
            mime = 'audio/mpeg'
            fe.enclosure(url, str(entry['duration']), mime)
            fe.link(href=url, type=mime)
        fg.rss_str(pretty=True)
        fg.rss_file(os.path.join(CACHE_DIR, output))

    def _load(self):
        try:
            with open(MANIFEST, 'r') as m:
                manifest = yaml.load(m.read()) or {}
        except FileNotFoundError:
            manifest = {}
        return manifest

    def _save(self, manifest):
        with open(MANIFEST, 'w') as m:
            m.write( yaml.dump(manifest) )


class Article(object):
    _audio = None

    def __init__(self, item_node):
        self.title = item_node.find('title').text
        self.description = item_node.find('description').text
        self.link = item_node.find('link').text
        self.enclosure = item_node.find('enclosure').attrib['url']
        self.guid = item_node.find('guid').text
        self.local = os.path.join(CACHE_DIR, self.guid)

    @property
    def audio(self):
        self.download()
        return AudioSegment.from_file(self.local, format=FORMAT)

    @property
    def mnemonic(self):
        return self._parse_guid().group('mne')

    @property
    def lang(self):
        return self._parse_guid().group('lang')

    @property
    def issue_date(self):
        return self._parse_guid().group('issue')

    @property
    def track(self):
        return self._parse_guid().group('track')

    @property
    def hashseed(self):
        return self.guid

    def _parse_guid(self):
        return re.match('^(?P<mne>[a-z]+)_(?P<lang>[A-Z]+)_(?P<issue>\d{6,8})_(?P<track>[\d]+)', self.guid)

    def download(self):
        if os.path.exists(self.local):
            return
        with open(self.local, 'wb') as cache:
            resp = requests.get(self.enclosure, stream=True)
            cache.write(resp.content)
        print("Downloaded %s" % self.guid)

    def __str__(self):
        return "<Article guid='%s' title='%s'>" % (self.guid, self.title)


class Issue(object):
    def __init__(self, articles):
        self.articles = sorted(articles, key=lambda a: a.track)
        self.local = os.path.join(CACHE_DIR, "%s_%s_%s.%s" % (self.mnemonic, self.lang, self.issue_date, FORMAT))

    @property
    def mnemonic(self):
        return self.articles[0].mnemonic

    @property
    def lang(self):
        return self.articles[0].lang

    @property
    def issue_date(self):
        return self.articles[0].issue_date

    @property
    def hashseed(self):
        return ''.join(a.hashseed for a in self.articles)

    @property
    def hash(self):
        return hashlib.md5(self.hashseed.encode('utf8')).hexdigest()

    @property
    def title(self):
        return "%s%s %s – %s" % (self.mnemonic, self.lang, self.issue_date, self.articles[0].title)

    def create_combined_audio(self, manifest):
        if manifest.get_issue_hash(self) == self.hash:
            print("%s: Combined audio already exists" % self)
            return

        if len(self.articles) < manifest.get_article_count(self):
            print("%s: Feed has fewer articles (%s) then preexisting combined audio (%s)." % (self, len(self.articles), manifest.get_article_count(self)))
            return

        for article in self.articles:
            article.download()

        combined = AudioSegment.empty()
        for article in self.articles:
            print("%s: Found %s with length of %s seconds" % (self, article, article.audio.duration_seconds))
            combined += article.audio

        combined.export(self.local, format=FORMAT, bitrate="128k")
        manifest.save_issue(self, combined)
        print("%s: Created combined audio with length of %s seconds" % (self, combined.duration_seconds))
        print("%s: Saved to %s" % (self, self.local))

    def __str__(self):
        return "<Issue mnemonic='%s' date='%s' length='%d'>" % (self.mnemonic, self.issue_date, len(self.articles))


class RSSFeedReader(object):
    _doc = None

    def __init__(self, language, mnemonic):
        self.language = language
        self.mnemonic = mnemonic
        self.url = "https://www.jw.org/apps/E_RSSMEDIAMAG?rln=%s&rmn=%s&rfm=%s" % (language, mnemonic, FORMAT)

    @property
    def articles(self):
        doc = self._fetch()
        for item in doc.findall('channel/item'):
            yield Article(item)

    @property
    def issues(self):
        issues = {}
        for article in self.articles:
            if article.issue_date not in issues:
                issues[article.issue_date] = []
            issues[article.issue_date].append(article)
        return (Issue(articles) for articles in issues.values())

    def _fetch(self):
        if not self._doc:
            resp = requests.get(self.url)
            resp.raise_for_status()
            self._doc = etree.fromstring(resp.text)
        return self._doc



if __name__ == "__main__":
    manifest = Manifest()
    for lang in LANGUAGES:
        for mnemonic in MNEMONICS:
            for issue in RSSFeedReader(lang, mnemonic).issues:
                issue.create_combined_audio(manifest)
    manifest.export_feed('feed.atom')
    manifest.prune()
