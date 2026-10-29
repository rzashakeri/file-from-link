import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.ig_urls import upscale_cdn_url, pick_pic_url, hd_info_url

def test_upscale_rewrites_size_segment():
    url = "https://scontent.cdninstagram.com/v/t51.2885-19/123_s320x320.jpg?x=1"
    assert upscale_cdn_url(url) == "https://scontent.cdninstagram.com/v/t51.2885-19/123_s1080x1080.jpg?x=1"
    url2 = "https://scontent.cdninstagram.com/v/t51.2885-19/s320x320/123.jpg"
    assert upscale_cdn_url(url2) == "https://scontent.cdninstagram.com/v/t51.2885-19/s1080x1080/123.jpg"
    url3 = "https://scontent.cdninstagram.com/v/t51.2885-19/123.jpg?stp=dst-jpg_e35_s320x320"
    assert upscale_cdn_url(url3) == "https://scontent.cdninstagram.com/v/t51.2885-19/123.jpg?stp=dst-jpg_e35_s1080x1080"

def test_upscale_leaves_url_without_size_segment():
    url = "https://scontent.cdninstagram.com/v/t51.2885-19/123.jpg"
    assert upscale_cdn_url(url) == url
    assert upscale_cdn_url("") == ""

def test_pick_pic_url_prefers_hd():
    assert pick_pic_url({"profile_pic_url": "small", "profile_pic_url_hd": "hd"}) == "hd"
    assert pick_pic_url({"profile_pic_url": "small"}) == "small"
    assert pick_pic_url({}) is None
    assert pick_pic_url(None) is None

def test_hd_info_url_prefers_hd_info():
    assert hd_info_url({"hd_profile_pic_url_info": {"url": "hd", "width": 1080}, "profile_pic_url": "small"}) == "hd"
    assert hd_info_url({"profile_pic_url": "small"}) == "small"
    assert hd_info_url({}) is None
