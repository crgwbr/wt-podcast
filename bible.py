#!/usr/bin/env python3

from datetime import datetime, timedelta
from dateutil.parser import parse
from feedgen.feed import FeedGenerator
import pytz
import requests
import os.path
import os


BIBLE_PUB = 'nwt'

CACHE_DIR = os.environ.get('CACHE_DIR')
if not CACHE_DIR:
    CACHE_DIR = os.path.join(os.path.dirname(__file__), '_cache')

URL_BASE = os.environ.get('URL_BASE')
if not URL_BASE:
    URL_BASE = 'https://crgwbr.com/jworg-magazines'



def list_books(language, file_format):
    books_resp = requests.get('https://apps.jw.org/GETPUBMEDIALINKS', params={
        'langwritten': language,
        'txtCMSLang': language,
        'alllangs': 0,
        'pub': BIBLE_PUB,
        'booknum': 0,
        'fileformat': file_format,
        'output': 'json',
    })
    books_resp.raise_for_status()
    books = books_resp.json()['files'][language][file_format]
    return sorted(books, key=lambda b: b['booknum'])



def list_chapters(language, file_format, booknum):
    chapters_resp = requests.get('https://apps.jw.org/GETPUBMEDIALINKS', params={
        'langwritten': language,
        'txtCMSLang': language,
        'alllangs': 0,
        'pub': BIBLE_PUB,
        'booknum': booknum,
        'fileformat': file_format,
        'output': 'json',
    })
    chapters_resp.raise_for_status()
    chapters = chapters_resp.json()['files'][language][file_format]
    # Skip track 0 since thats a ZIP file of all the MP3
    return sorted([c for c in chapters if c['track'] != 0], key=lambda b: b['track'])



def main(output='nwt.atom'):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.podcast.itunes_category('Religion & Spirituality', 'Christianity')
    fg.podcast.itunes_image('https://www.jw.org/assets/a/nwt/E/wpub/nwt_E_lg.jpg')
    fg.title('New World Translation of the Holy Scriptures (2013 Revision)')
    fg.description('Audio of the "New World Translation of the Holy Scriptures (2013 Revision)" from jw.org.')
    fg.link(href="{}{}".format(URL_BASE, output), rel='self')

    language = 'E'
    file_format = 'MP3'
    for book in list_books(language, file_format):
        booknum = book['booknum']
        title = book['title']
        for chapter in list_chapters(language, file_format, booknum):
            track_id = "{}-{}".format(booknum, chapter['track'])
            track_title = "{} {}".format(title, chapter['title'])

            modified_datetime = pytz.utc.localize(parse(chapter['file']['modifiedDatetime']))

            ordering_offset = int(str(booknum).zfill(2) + str(chapter['track']).zfill(3))
            published_datetime = datetime(2013, 10, 5, tzinfo=pytz.UTC) + timedelta(seconds=ordering_offset)

            url = chapter['file']['url']
            duration = chapter['duration']
            mimetype = chapter['mimetype']

            fe = fg.add_entry()
            fe.id(track_id)
            fe.title(track_title)
            fe.description(track_title)
            fe.updated(modified_datetime)
            fe.published(published_datetime)
            fe.enclosure(url, str(duration), mimetype)
            fe.link(href=url, type=mimetype)
            print(track_title)

    fg.rss_str(pretty=True)
    fg.rss_file(os.path.join(CACHE_DIR, output))



if __name__ == "__main__":
    main()
