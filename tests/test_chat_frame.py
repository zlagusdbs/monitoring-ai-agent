from web import server


def test_plain_text_frame_still_works():
    assert server._unpack("안녕") == ("안녕", [])


def test_json_frame_splits_text_and_images():
    text, images = server._unpack(
        '{"text":"이거 봐줘","images":[{"media_type":"image/png","data":"AAA"}]}')
    assert text == "이거 봐줘" and len(images) == 1


def test_unknown_media_type_is_dropped():
    _, images = server._unpack(
        '{"text":"x","images":[{"media_type":"application/pdf","data":"AAA"}]}')
    assert images == []


def test_at_most_three_images():
    many = ",".join(['{"media_type":"image/png","data":"A"}'] * 5)
    _, images = server._unpack('{"text":"x","images":[' + many + "]}")
    assert len(images) == 3


def test_oversized_image_is_dropped():
    big = "A" * (4 * 1024 * 1024 * 4 // 3 + 10)
    _, images = server._unpack(
        '{"text":"x","images":[{"media_type":"image/png","data":"' + big + '"}]}')
    assert images == []
