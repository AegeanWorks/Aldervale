"""Truecolor pixel frame buffer and baked pixel sprites.

The graphics build replaces the char-cell surface with a square-pixel RGB
buffer.  Columns are stored contiguously so the terrain march can fill a
vertical run with one slice assignment; the browser client transposes the
buffer into an ImageData once per frame.
"""

from .buffer import FAR


class FrameBuffer:
    """A w x h truecolor image plus a per-pixel depth buffer (column-major)."""

    __slots__ = ("w", "h", "data", "depth", "_col_stride", "_depth_stride")

    def __init__(self, w, h):
        self.w = int(w)
        self.h = int(h)
        self.data = bytearray(self.w * self.h * 3)
        self.depth = [FAR] * (self.w * self.h)
        self._col_stride = self.h * 3
        self._depth_stride = self.h

    def clear(self, color=0):
        r = (color >> 16) & 255
        g = (color >> 8) & 255
        b = color & 255
        self.data[:] = bytes((r, g, b)) * (self.w * self.h)
        self.depth[:] = [FAR] * (self.w * self.h)

    def set(self, x, y, color, depth=FAR):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._col_stride * x + y * 3
            self.data[o] = (color >> 16) & 255
            self.data[o + 1] = (color >> 8) & 255
            self.data[o + 2] = color & 255
            self.depth[self._depth_stride * x + y] = depth

    def blend(self, x, y, color, alpha, depth=None):
        """Alpha-blend a colour over one pixel; optionally write its depth."""
        if alpha <= 0.02 or not (0 <= x < self.w and 0 <= y < self.h):
            return
        if alpha > 1.0:
            alpha = 1.0
        o = self._col_stride * x + y * 3
        d = self.data
        d[o] = int(d[o] + (((color >> 16) & 255) - d[o]) * alpha)
        d[o + 1] = int(d[o + 1] + (((color >> 8) & 255) - d[o + 1]) * alpha)
        d[o + 2] = int(d[o + 2] + ((color & 255) - d[o + 2]) * alpha)
        if depth is not None:
            self.depth[self._depth_stride * x + y] = depth

    def add(self, x, y, color, alpha):
        """Additive blend used by emissive sprites and light pools."""
        if alpha <= 0.02 or not (0 <= x < self.w and 0 <= y < self.h):
            return
        o = self._col_stride * x + y * 3
        d = self.data
        d[o] = min(255, int(d[o] + ((color >> 16) & 255) * alpha))
        d[o + 1] = min(255, int(d[o + 1] + ((color >> 8) & 255) * alpha))
        d[o + 2] = min(255, int(d[o + 2] + (color & 255) * alpha))

    def fill_column(self, x, y0, y1, color, depth=FAR):
        """Fill a clipped vertical run [y0, y1) in one column."""
        if x < 0 or x >= self.w:
            return
        if y0 < 0:
            y0 = 0
        if y1 > self.h:
            y1 = self.h
        if y1 <= y0:
            return
        n = y1 - y0
        o = self._col_stride * x + y0 * 3
        self.data[o:o + n * 3] = bytes(((color >> 16) & 255,
                                        (color >> 8) & 255,
                                        color & 255)) * n
        d0 = self._depth_stride * x + y0
        self.depth[d0:d0 + n] = [depth] * n

    def fill_column_pattern(self, x, y0, y1, pattern, depth=FAR, phase=0):
        """Fill a vertical run with a repeating RGB strip (world texture)."""
        if x < 0 or x >= self.w or not pattern:
            return
        if y0 < 0:
            y0 = 0
        if y1 > self.h:
            y1 = self.h
        if y1 <= y0:
            return
        rows = len(pattern) // 3
        if rows < 1:
            return
        phase %= rows
        if phase:
            pattern = pattern[phase * 3:] + pattern[:phase * 3]
        n = y1 - y0
        reps, rem = divmod(n, rows)
        strip = pattern * reps + pattern[:rem * 3]
        o = self._col_stride * x + y0 * 3
        self.data[o:o + n * 3] = strip
        d0 = self._depth_stride * x + y0
        self.depth[d0:d0 + n] = [depth] * n

    def fill(self, color):
        self.clear(color)

    def column_depth(self, x):
        base = self._depth_stride * x
        return self.depth[base:base + self.h]

    def sample_depth(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.depth[self._depth_stride * x + y]
        return FAR

    def to_row_major(self, scale=1):
        """Return (width, height, rgb bytes) for PNG/browser presentation."""
        scale = max(1, int(scale))
        w, h = self.w, self.h
        out = bytearray(w * scale * h * scale * 3)
        dst_w = w * scale
        src = self.data
        for y in range(h):
            row = bytearray(w * 3)
            for x in range(w):
                o = self._col_stride * x + y * 3
                row[x * 3:x * 3 + 3] = src[o:o + 3]
            if scale == 1:
                out[y * dst_w * 3:(y + 1) * dst_w * 3] = row
            else:
                big = bytearray()
                for x in range(w):
                    pixel = row[x * 3:x * 3 + 3]
                    big.extend(pixel * scale)
                line = bytes(big)
                start = y * scale * dst_w * 3
                for sy in range(scale):
                    o = start + sy * dst_w * 3
                    out[o:o + len(line)] = line
        return w * scale, h * scale, bytes(out)


class PixelSprite:
    """A baked RGBA billboard plus an optional additive glow layer."""

    __slots__ = ("w", "h", "rgba", "glow")

    def __init__(self, w, h, rgba, glow=None):
        self.w = w
        self.h = h
        self.rgba = rgba
        self.glow = glow

    def filled(self):
        return sum(1 for i in range(3, len(self.rgba), 4) if self.rgba[i])
