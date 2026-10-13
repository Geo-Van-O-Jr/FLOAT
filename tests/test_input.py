import ctypes
from float_app.windows import InputExecutor, INPUT


def recorder():
    executor = InputExecutor()
    events = []
    executor.send = lambda inputs: events.extend(inputs)
    return executor, events


def test_unicode_injection_has_utf16_down_up_pairs():
    executor, events = recorder()
    executor.text("ação 😀")
    units = "ação 😀".encode("utf-16-le")
    assert len(events) == len(units)
    restored = b"".join(int(e.ki.wScan).to_bytes(2, "little") for e in events[::2])
    assert restored.decode("utf-16-le") == "ação 😀"
    assert all(e.ki.dwFlags == 4 for e in events[::2])
    assert all(e.ki.dwFlags == 6 for e in events[1::2])
    assert ctypes.sizeof(INPUT) == 40


def test_release_all_does_not_leave_drag_down():
    executor, events = recorder()
    executor.button("left", True)
    executor.release_all()
    executor.release_all()
    assert [e.mi.dwFlags for e in events] == [2, 4]
    assert executor.held == set()


def test_shortcut_releases_keys_in_reverse_order():
    executor, events = recorder()
    executor.key("ctrl+shift+z")
    assert [e.ki.wVk for e in events] == [17, 16, ord("Z"), ord("Z"), 16, 17]
    assert [e.ki.dwFlags for e in events] == [0, 0, 0, 2, 2, 2]


def test_double_click_is_one_batch_of_four_events():
    executor, events = recorder()
    executor.click(count=2)
    assert [e.mi.dwFlags for e in events] == [2, 4, 2, 4]

