class InsecureProtocolError(Exception):
    def __init__(self, url, message="URL must use HTTPS"):
        self.url = url
        self.message = message
        super().__init__(self.message)
