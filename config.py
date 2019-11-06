import os
import configparser


class Config:
    def __init__(self):
        pass

    def getConfig(self, section, key):
        config = configparser.ConfigParser()
        rootPath = os.path.dirname(__file__)
        path = os.path.join(rootPath, 'config.conf')
        config.read(path)
        return config.get(section, key)