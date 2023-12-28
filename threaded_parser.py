import argparse
import os
import pathlib
import re
import signal
import sys
import urllib.request
import threading
from typing import Optional
from urllib.error import URLError, HTTPError

har = "https://habr.com"


class GracefulShutdown:
    def __init__(self, thread):
        self.threads = thread
        self.event = threading.Event()
        signal.signal(signal.SIGINT, self.exit_graceful)
        signal.signal(signal.SIGTERM, self.exit_graceful)

    def exit_graceful(self, signum, frame):
        self.event.set()
        wait_threads(self.threads)


def wait_threads(threads):
    while len(threads) > 0:
        thread = threads.pop()
        thread.join()


def validate_dir(path):
    prohibited_chars = '<>"/\|?*:. '
    for char in path:
        if char in prohibited_chars:
            path = path.replace(char, '_')
    return path


def download_images(name_article, article_ref):
    images = get_images(article_ref)

    if not images:
        return None

    name_article = validate_dir(name_article)
    os.makedirs(name_article, exist_ok=True)

    for ref in images:
        try:
            image_content = urllib.request.urlopen(ref)
            image_name = ref[ref.rfind('/') + 1:]
            path = os.path.join(name_article, image_name)
            image_descriptor = open(path, 'wb')
            image_descriptor.write(image_content.read())
            image_descriptor.close()
        except (HTTPError, URLError):
            return None


def get_images(article_ref):
    try:
        content = urllib.request.urlopen(har + article_ref, timeout=10).read().decode('utf-8')
        body_start = content.find('<div id="post-content-body">')
        body_end = content.find('</div>', body_start)
        good_content = content[body_start:body_end]
        re_images = re.compile(r'<img src=\"')
        all_images = re.finditer(re_images, good_content)
        clear_images = []
        for image in all_images:
            start_ref = image.end()
            end_ref = good_content.find(f'"', start_ref)
            clear_images.append(good_content[start_ref:end_ref])
        return clear_images
    except (HTTPError, URLError):
        return None


def load_content(url: str) -> Optional[bytes]:
    try:
        return urllib.request.urlopen(url, timeout=10).read()
    except (HTTPError, URLError):
        return None


def run_scraper(threads: int, articles: int, out_dir: pathlib.Path) -> None:
    thread = []
    grate_shutdown = GracefulShutdown(thread)

    if os.path.exists(out_dir):
        os.chdir(out_dir)

    content = load_content(har).decode("utf-8")
    re_headers = re.compile(r'<h2.*<\/h2>')
    re_name = re.compile(r'(<span>)(.*)(<\/span>)')
    re_href = re.compile(r'<a href=\"(.*)\"')
    article_list = re.findall(re_headers, content)[:articles]  # Берем последние n статей

    for ref in article_list:
        if not grate_shutdown.event.is_set():
            while len(thread) >= threads:
                for cur_thread in thread:
                    if not cur_thread.is_alive():
                        thread.remove(cur_thread)
                        break
        else:
            break

        article_name = re.search(re_name, ref).group(2)
        article_ref = re.search(re_href, ref).group(1)  # Сделано из-за жадности регулярки
        article_ref = article_ref[:article_ref.find(f'"', 1)]
        cur_thread = threading.Thread(target=download_images(article_name, article_ref))
        thread.append(cur_thread)
        cur_thread.start()
    wait_threads(thread)


def main():
    script_name = os.path.basename(sys.argv[0])
    parser = argparse.ArgumentParser(
        usage=f'{script_name} [ARTICLES_NUMBER] THREAD_NUMBER OUT_DIRECTORY',
        description='Habr parser',
    )
    parser.add_argument(
        '-n', type=int, default=25, help='Number of articles to be processed',
    )
    parser.add_argument(
        'threads', type=int, help='Number of threads to be run',
    )
    parser.add_argument(
        'out_dir', type=pathlib.Path, help='Directory to download habr images',
    )
    args = parser.parse_args()

    run_scraper(args.threads, args.n, args.out_dir)


if __name__ == '__main__':
    main()
