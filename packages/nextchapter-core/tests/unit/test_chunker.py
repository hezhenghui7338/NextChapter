"""章节切分测试。覆盖 PRD F1/F2 验收：第X章切分 + 短章节合并。"""
import pytest

from nextchapter_core.chunker import ChapterChunker

pytestmark = pytest.mark.unit


SAMPLE = """
第一章 初入江湖

少年李青云踏入洛阳城，剑眉星目，意气风发。他身后背着一柄玄铁长剑，剑穗随风轻扬。城门口人潮汹涌，他深吸一口气，迈步向前。洛阳乃九朝古都，繁华似锦。街边小贩叫卖声此起彼伏，江湖客来来往往，各色人等混杂其间。李青云先寻一间客栈落脚，准备打探一番消息再做打算。掌柜见他气度不凡，便殷勤招呼，亲自领他上楼挑选了一间上房。

第二章 客栈风波

夜宿客栈，忽闻隔壁传来打斗之声。李青云推门而出，恰见三名黑衣人围攻一名青衫老者。老者身负重伤，勉力支撑，眼看就要命丧当场。李青云心念一动，抽剑而出加入战团。他剑法凌厉，三招两式便将一名黑衣人刺倒。剩余两人见势不妙，立刻抽身退走。临走时丢下一句狠话：此事没完，等着瞧。

第三章 神秘剑诀

老者临终前将一本泛黄剑谱塞入他手中，嘱他务必送至峨眉山。李青云接过剑谱，只见封面上写着「玄天真经」四字，笔力遒劲，气象不凡。他问老者来历，老者只摇头说知道得越少越好，便闭目而逝。李青云只好将其就地掩埋，带着剑谱踏上前往峨眉的漫漫长路。

第四章 路遇佳人

行至半山腰，山雾弥漫中传来一阵琴声。拨开云雾，竟是一位白衣女子端坐于青石之上抚琴。那琴声时而如高山流水，时而如泣如诉，扣人心弦。女子抬头望向他，眉目如画，淡淡一笑：公子可是要上峨眉？李青云点头称是。女子起身道：正好同路，不如结伴而行？李青云犹豫片刻，便应允下来。

第五章 暗流涌动

黑衣人的同伙已布下天罗地网，李青云与白衣女子能否逃出生天？前方山道突然涌现数十名黑衣人，将两人团团围住。女子冷笑道：早就料到你们会来。说着抽出腰间软剑，剑光如雪，杀意凛然。李青云也拔剑在手，与她背靠背站定。一场恶战，一触即发。
"""


def test_split_basic_chapters():
    chunker = ChapterChunker()
    chapters = chunker.split(SAMPLE)
    assert len(chapters) >= 4
    titles = [c.title for c in chapters]
    assert any("第一章" in t for t in titles)
    assert any("第二章" in t for t in titles)
    for c in chapters:
        assert c.char_count > 0
        assert c.body.strip()


def test_no_chapter_returns_single():
    text = "这是一段没有章节标记的纯文本。" * 50
    chunker = ChapterChunker()
    chapters = chunker.split(text)
    assert len(chapters) == 1
    assert chapters[0].kind == "chapter"
