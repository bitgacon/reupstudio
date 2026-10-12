import pytest
from reup.word_timing import align_reference

def words(*tokens):return [{'word':w,'start':i*200,'end':i*200+150} for i,w in enumerate(tokens)]

def test_reuse_audio_onsets_with_reference_punctuation():
    result=align_reference('Xin chào, bạn!',words('Xin','chào','bạn'))
    assert result['can_apply'] and result['coverage']==1
    assert result['words'][1]=={'word':'chào,','start':200,'end':350}

def test_missing_translation_is_not_assigned_fake_timing():
    result=align_reference('Xin chào mọi người',words('Xin','chào','bạn'))
    assert not result['can_apply'] and result['coverage']==.5
    assert [w['word'] for w in result['unmatched']]==['mọi','người']
    assert [w['word'] for w in result['words']]==['Xin','chào']

def test_cross_language_does_not_pretend_alignment():
    result=align_reference('Xin chào bạn',words('你好'))
    assert not result['can_apply'] and result['coverage']==0 and result['words']==[]

def test_repeated_words_keep_monotonic_original_onsets():
    result=align_reference('xin xin chào',words('xin','xin','chào'))
    assert [w['start'] for w in result['words']]==[0,200,400]

def test_reference_limits():
    with pytest.raises(ValueError):align_reference('x '*401,words('x'))
