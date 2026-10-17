"""Map camera in world metres, independent of Tk and the telemetry source."""
import math


class MapCamera:
    MIN_ZOOM = .4
    MAX_ZOOM = 80.0

    def __init__(self):
        self.width, self.height = 500.0, 350.0
        self.fit_center = (0.0, 0.0)
        self.fit_scale = 1.0
        self.center = (0.0, 0.0)
        self.scale = 1.0
        self.overview = True
        self.follow = False
        self.ready = False

    @property
    def zoom(self):
        return self.scale / self.fit_scale

    def update(self, bounds, width, height, target=None):
        self.width, self.height = max(1, width), max(1, height)
        a, b, c, d = bounds
        self.fit_center = ((a + c) / 2, (b + d) / 2)
        self.fit_scale = max(1e-8, min(max(1, width - 50) / max(50, c - a),
                                       max(1, height - 70) / max(50, d - b)))
        if self.overview or not self.ready:
            self.center, self.scale = self.fit_center, self.fit_scale
            self.ready = True
        if self.follow and target is not None:
            self.center = tuple(target)

    def project(self, x, y):
        return (self.width / 2 + (x - self.center[0]) * self.scale,
                self.height / 2 - (y - self.center[1]) * self.scale)

    def unproject(self, x, y):
        return (self.center[0] + (x - self.width / 2) / self.scale,
                self.center[1] - (y - self.height / 2) / self.scale)

    def fit_all(self):
        self.overview, self.follow = True, False
        self.center, self.scale = self.fit_center, self.fit_scale

    def set_follow(self, enabled, target=None):
        self.follow = bool(enabled)
        self.overview = False
        if enabled and target is not None:
            self.center = tuple(target)

    def focus(self, target=None):
        self.set_follow(True, target)
        if self.zoom < 4:
            self.scale = self.fit_scale * 8

    def pan(self, dx, dy):
        self.overview, self.follow = False, False
        self.center = (self.center[0] - dx / self.scale,
                       self.center[1] + dy / self.scale)

    def wheel(self, factor, x=None, y=None):
        if not math.isfinite(factor) or factor <= 0:
            return
        x = self.width / 2 if x is None else x
        y = self.height / 2 if y is None else y
        anchor = self.unproject(x, y)
        scale = self.fit_scale * max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom * factor))
        if not self.follow:
            self.center = (anchor[0] - (x - self.width / 2) / scale,
                           anchor[1] + (y - self.height / 2) / scale)
        self.scale, self.overview = scale, False
