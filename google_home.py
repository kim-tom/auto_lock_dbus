import requests
class google_home:
    @classmethod
    def notify(cls, mp3_url):
        try:
            requests.get(mp3_url, timeout=(0.5, 2.0))
        except requests.exceptions.RequestException as e:
            print("GHN Server:", e.__doc__.strip())
