# Copyright 2023 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from PySide6 import QtWidgets, QtGui, QtCore
from joulescope_ui import N_, register
from joulescope_ui.styles import styled_widget, color_as_qcolor, font_as_qfont
import numpy as np
import os
import psutil


_TOPIC = 'registry/JsdrvStreamBuffer:001/settings/size'
_GB_FACTOR = 1024 ** 3
_SZ_MIN = int(0.01 * _GB_FACTOR)


def _mem_proc():
    return psutil.Process(os.getpid()).memory_info().rss


def _format(sz):
    sz = sz / _GB_FACTOR
    return f'{sz:.2f}'


class MemSet(QtWidgets.QWidget):

    def __init__(self, parent=None):
        self._parent = parent
        self.sizes = np.array([0, 0, 0, 1], dtype=float)
        super().__init__(parent=parent)
        self._height = 30
        self._x_pos = 0
        self._drag = None
        self._width = 1
        self.setMinimumHeight(self._height)
        self.setMaximumHeight(self._height)
        self.setMouseTracking(True)
        self._CURSOR_ARROW = QtGui.QCursor(QtGui.Qt.ArrowCursor)
        self._CURSOR_SIZE_HOR = QtGui.QCursor(QtGui.Qt.SizeHorCursor)

    @property
    def is_active(self):
        return self._drag is not None

    def update(self, base, available, used):
        if self._drag is None:
            self.sizes[0] = base
            self.sizes[2] = available
            self.sizes[3] = used
            self.repaint()

    def update_size(self, size):
        if self._drag is None:
            self.sizes[1] = size

    def show_size(self, size):
        self._parent._on_size(size)
        self.repaint()

    def _pixel_boundaries(self):
        w = self.width()
        sizes = np.array(self.sizes, dtype=float)
        total = np.sum(sizes)
        pixels = np.rint(sizes * (w / total)).astype(np.uint64)
        return pixels

    def paintEvent(self, event):
        if not hasattr(self._parent, 'style_manager_info'):
            return
        v = self._parent.style_manager_info['sub_vars']
        widget_w, widget_h = self.width(), self.height()
        p = QtGui.QPainter(self)

        pixels = self._pixel_boundaries()
        self._width = np.sum(pixels)

        colors = [
            color_as_qcolor(v['memory.base']),
            color_as_qcolor(v['memory.size']),
            color_as_qcolor(v['memory.available']),
            color_as_qcolor(v['memory.used']),
        ]

        x = 0
        for idx, pixel in enumerate(pixels):
            b1 = QtGui.QBrush(colors[idx])
            p.setBrush(b1)
            if pixel:
                p.fillRect(x, 0, pixel, widget_h, b1)
            x += pixel
            if idx == 1:
                self._x_pos = x

    def is_mouse_active(self, x):
        return abs(x - self._x_pos) < 10

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        x = event.pos().x()
        if self.is_mouse_active(x):
            cursor = self._CURSOR_SIZE_HOR
        else:
            cursor = self._CURSOR_ARROW
        self.setCursor(cursor)
        if self._drag is not None:
            total = np.sum(self.sizes)
            sz = x / self._width * total - self.sizes[0]
            sz_max = self.sizes[1] + self.sizes[2]
            sz = max(_SZ_MIN, min(sz, sz_max))
            dsz = sz - self.sizes[1]
            self.sizes[1] += dsz
            self.sizes[2] -= dsz
            self.show_size(sz)

    def abort(self):
        if self._drag is None:
            return
        self.show_size(self._drag[1])
        self.sizes, self._drag = self._drag, None

    def mousePressEvent(self, event):
        event.accept()
        x = event.pos().x()
        if event.button() == QtCore.Qt.LeftButton:
            if self._drag is None and self.is_mouse_active(x):
                self._drag = np.copy(self.sizes)
        elif self._drag is not None:
            self.abort()
        self.repaint()

    def mouseReleaseEvent(self, event):
        event.accept()
        if self._drag is None:
            return
        if event.button() == QtCore.Qt.LeftButton:
            self._parent.size = self.sizes[1]
            self._drag = None
        else:
            self.abort()


@register
@styled_widget(N_('Memory'))
class MemoryWidget(QtWidgets.QWidget):
    CAPABILITIES = ['widget@']

    def __init__(self, parent=None):
        self._on_size_fn = self._on_size
        self._base = 0
        self._size = 0  # in bytes
        self._used = 0
        super().__init__(parent=parent)
        self.setObjectName('memory_widget')
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self._layout = QtWidgets.QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)

        self._memset = MemSet(self)
        self._layout.addWidget(self._memset)

        self._grid_widget = QtWidgets.QWidget(parent=self)
        self._grid_layout = QtWidgets.QGridLayout()
        self._grid_widget.setLayout(self._grid_layout)
        self._layout.addWidget(self._grid_widget)

        vm = psutil.virtual_memory()
        self._widgets = {
            'size_label': QtWidgets.QLabel(N_('Memory buffer size'), self._grid_widget),
            'size_value': QtWidgets.QLabel(f'0', self._grid_widget),
            'size_units': QtWidgets.QLabel('GB', self._grid_widget),
            'total_label': QtWidgets.QLabel(N_('Total RAM size'), self._grid_widget),
            'total_value': QtWidgets.QLabel(_format(vm.total), self._grid_widget),
            'total_units': QtWidgets.QLabel('GB', self._grid_widget),
            'available_label': QtWidgets.QLabel(N_('Available RAM size'), self._grid_widget),
            'available_value': QtWidgets.QLabel(f'0', self._grid_widget),
            'available_units': QtWidgets.QLabel('GB', self._grid_widget),
            'used_label': QtWidgets.QLabel(N_('Used RAM size'), self._grid_widget),
            'used_value': QtWidgets.QLabel(f'0', self._grid_widget),
            'used_units': QtWidgets.QLabel('GB', self._grid_widget),
        }

        for row, s in enumerate(['size', 'available', 'used', 'total']):
            self._grid_layout.addWidget(self._widgets[f'{s}_label'], row, 0)
            self._grid_layout.addWidget(self._widgets[f'{s}_value'], row, 1)
            self._grid_layout.addWidget(self._widgets[f'{s}_units'], row, 2)

        self._spacer = QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self._layout.addItem(self._spacer)

        self._timer = None

    def _update(self, size=None):
        if size is None:
            size = self._size
        vm = psutil.virtual_memory()
        my_mem = psutil.Process(os.getpid()).memory_info().rss

        used = vm.used - my_mem
        s = _format(used)
        self._widgets['used_value'].setText(s)

        available = vm.total - (self._base + size + used)
        s = _format(available)
        self._widgets['available_value'].setText(s)
        self._memset.update(self._base, available, used)

    def on_pubsub_register(self):
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(100)

    def _on_timer(self):
        if self._base == 0:
            mem = _mem_proc()
            sz = self.pubsub.query(_TOPIC)
            if mem > sz:
                self._base = mem - sz
            else:
                self._base = mem
            self.pubsub.subscribe(_TOPIC, self._on_size_fn, ['pub', 'retain'])
            self._timer.start(1000)
        if not self._memset.is_active:
            self._update()

    def closeEvent(self, event):
        self.pubsub.unsubscribe(_TOPIC, self._on_size_fn)
        return super().closeEvent(event)

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, value):
        self.pubsub.publish(_TOPIC, int(value))

    def _on_size(self, value):
        self._size = int(value)
        s = _format(self._size)
        self._widgets['size_value'].setText(s)
        self._memset.update_size(value)
        self._update(value)