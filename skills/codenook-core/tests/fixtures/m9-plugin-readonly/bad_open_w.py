"""Fixture: contains a literal write into plugins/ — must be flagged
by the plugin_readonly checker (TC-M9.7-02).
"""
def write_bad():
    open("plugins/foo.txt", "w").write("nope")
