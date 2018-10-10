# -*- coding: utf-8 -*-
import urllib.parse
import urllib.request
import youtube_dl
import subprocess
import os
import os.path
import time
from adapt.intent import IntentBuilder
from bs4 import BeautifulSoup
from mycroft import intent_file_handler
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel

class AVmusicSkill(CommonPlaySkill):
    def __init__(self):
        super().__init__(name="AVmusicSkill")

        self.process = None
        self.search_results = {}
        self.info_dict = {}
        self.tmpl = "/tmp/AVmusic"
        self.tmp_file = None
        self.eta = None

    def CPS_match_query_phrase(self, phrase):
        # Youtube with find a result for ANYTHING.  So there is no need to
        # wait for an actual search to happen, just assume we'll get a hit.
        if self.voc_match(phrase.lower(), "Youtube"):
            return (phrase, CPSMatchLevel.MULTI_KEY, None)
        else:
            return (phrase, CPSMatchLevel.GENERIC, None)

    def CPS_start(self, phrase, data):
        # Search Youtube for the videos matching the search
        self.enclosure.mouth_text("Searching Youtube...")
        try:
            url = self.search(phrase)

            # Download the results...
            self.enclosure.mouth_text("Downloading...")
            ydl_opts = {
                # Download audio only
                'format': 'bestaudio/best',

                # Output to this filename
                'outtmpl': self.tmpl,

                # Progress sent here
                'progress_hooks': [self.progress_hook]
            }
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                self.info_dict = ydl.extract_info(url)

            # Verify what was returned by YoutubeDL
            self.tmp = self.tmpl
            if not os.path.isfile(self.tmp) and "ext" in self.info_dict:
                self.tmp = self.tmpl + "." + self.info_dict["ext"]
            if not os.path.isfile(self.tmp):
                # Assume parts were merged into a mkv file
                self.tmp = self.tmpl + ".mkv"

            # Begin playback via MPV
            self.process = subprocess.Popen(["mpv", "--no-video", self.tmp],
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.STDOUT)
            self.schedule_repeating_event(self._monitor_playing,
                                        None, 1,
                                        name='MonitorAVMusic')
            self._show_title()
        except Exception as e:
            self.log.error(repr(e))
            self.speak_dialog('TryAgain')
            self.stop()

    def progress_hook(self, d):
        if "_eta_str" in d:
            if self.eta is not d["_eta_str"]:
                self.eta = d["_eta_str"]
                self.enclosure.mouth_text(self.eta)

    def search(self, phrase):
        if phrase not in self.search_results:
            # Perform a Youtube search
            query = urllib.parse.quote(phrase)
            url = "https://www.youtube.com/results?search_query=" + query
            response = urllib.request.urlopen(url)
            html = response.read()
            soup = BeautifulSoup(html, "html.parser")

            # Parse the results, looking for any found videos
            self.search_results[phrase] = None
            for vid in soup.findAll(attrs={'class': 'yt-uix-tile-link'}):
                # Skip commercial videos
                if not vid['href'].startswith("https://googleads.g.doubleclick.net/‌​") \
                        and not vid['href'].startswith("/user") \
                        and not vid['href'].startswith("/channel"):
                    self.search_results[phrase] = "http://www.youtube.com/" + vid['href']
                    break

        return self.search_results[phrase]

    @intent_file_handler("youtube.intent")
    def handle_youtube(self, message):
        result = self.CPS_match_query_phrase(message.data["target"])
        if result:
            self.CPS_start(result[0], result[2])

    def _show_title(self):
        def has(x):
            return x in self.info_dict and self.info_dict[x]

        if has("artist") and has("track"):
            title = self.info_dict['artist'] + " : " + self.info_dict['track']
        elif has("track"):
            title = self.info_dict['track']
        elif has("title"):
            title = "Playing: " + self.info_dict['title']
        elif has("description"):
            title = "Playing: " + self.info_dict['description']
        else:
            title = "Playing from Youtube..."
        self.enclosure.mouth_text(title[:30])

    def _monitor_playing(self, message):
        if self.enclosure.display_manager.get_active() == '':
            self._show_title()

        exit_code = self.process.poll()
        if exit_code is not None:
            # completed
            self.stop()

    def stop(self):
        if self.process:
            self.cancel_scheduled_event("MonitorAVMusic")
            self.enclosure.mouth_reset()
            if self.process.poll() is None:  # None = still running
                self.process.terminate()
            self.process = None
            try:
                os.remove(self.tmp)
            except Exception:
                # Ignore this problem
                pass
            return True
        else:
            return False


def create_skill():
    return AVmusicSkill()
