"""Post URL normalisation. Short-link expansion is mocked; no network."""

import unittest
import urllib.error
from unittest import mock

from clipper import urls

FULL_TT = "https://www.tiktok.com/@me/video/7301234567890123456"


class NormalizeUrlTest(unittest.TestCase):
    def test_strips_query_fragment_and_trailing_slash(self):
        self.assertEqual(urls.normalize_url(FULL_TT + "/?is_from_webapp=1&sender_device=pc#x"),
                         FULL_TT)
        self.assertEqual(urls.normalize_url("https://www.instagram.com/reel/C0abcDEF/?igsh=xyz"),
                         "https://www.instagram.com/reel/C0abcDEF")
        self.assertEqual(urls.normalize_url("https://youtube.com/shorts/AbC123xyz?si=track"),
                         "https://youtube.com/shorts/AbC123xyz")

    def test_lowercases_host_forces_https_trims_whitespace(self):
        self.assertEqual(urls.normalize_url("  http://WWW.TikTok.com/@me/video/7301234567890123456 "),
                         FULL_TT)

    def test_path_case_is_preserved(self):
        # Shorts/Reels IDs are case-sensitive.
        self.assertTrue(urls.normalize_url("https://youtube.com/shorts/AbC").endswith("/AbC"))

    def test_youtube_watch_keeps_video_id(self):
        self.assertEqual(urls.normalize_url("https://www.youtube.com/watch?si=x&v=AbC123&t=4"),
                         "https://www.youtube.com/watch?v=AbC123")

    def test_expands_tiktok_short_links(self):
        for short in ("https://vm.tiktok.com/ZMabc123/", "https://vt.tiktok.com/ZSxyz/?k=1"):
            with mock.patch.object(urls, "expand_short_link",
                                   return_value=FULL_TT + "?_r=1&_t=8abc") as m:
                self.assertEqual(urls.normalize_url(short), FULL_TT)
                m.assert_called_once()

    def test_full_tiktok_url_is_not_expanded(self):
        with mock.patch.object(urls, "expand_short_link") as m:
            urls.normalize_url(FULL_TT)
            m.assert_not_called()

    def test_expansion_failure_is_an_error(self):
        with mock.patch.object(urls, "expand_short_link",
                               side_effect=urllib.error.URLError("offline")):
            with self.assertRaisesRegex(urls.UrlError, "paste the full URL"):
                urls.normalize_url("https://vm.tiktok.com/ZMabc123/")

    def test_expansion_to_non_post_page_is_an_error(self):
        with mock.patch.object(urls, "expand_short_link",
                               return_value="https://www.tiktok.com/login?redirect=x"):
            with self.assertRaisesRegex(urls.UrlError, "doesn't look like a post URL"):
                urls.normalize_url("https://vm.tiktok.com/ZMabc123/")

    def test_rejects_non_urls(self):
        with self.assertRaises(urls.UrlError):
            urls.normalize_url("tiktok.com/@me/video/1")


if __name__ == "__main__":
    unittest.main()
