import json, tempfile, unittest
from pathlib import Path
from lab import fixture,scan,patch,commit

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)/'sample';fixture(self.p)

    def test_independent_known_edges(self):
        r=scan(self.p)
        self.assertEqual(r['actual']['main.o'],['config.h','main.c'])
        self.assertEqual({(f['type'],f['dependency']) for f in r['findings']},{('MISSING','config.h'),('REDUNDANT','unused.h')})

    def test_unchanged_reuses_both_targets(self):
        r=scan(self.p,scan(self.p));self.assertEqual(r['reused'],['main.o','helper.o']);self.assertEqual(r['refreshed'],[])

    def test_include_added_invalidates_cache(self):
        old=scan(self.p)
        (self.p/'main.c').write_text('#include "extra.h"\n'+(self.p/'main.c').read_text());commit(self.p,'new include')
        r=scan(self.p,old)
        self.assertIn(['MISSING','main.o','extra.h'],r['added']);self.assertEqual(len(r['refreshed']),2)

    def test_patch_preserves_redundant_dependency(self):
        r=scan(self.p);diff,plan=patch(self.p,r)
        self.assertIn('+main.o: main.c unused.h config.h',diff)
        self.assertNotIn('-\tgcc',diff)
        self.assertNotIn('config.h',(self.p/'Makefile').read_text())

    def test_old_report_rejected(self):
        r=scan(self.p);r['commit']='0'*40
        with self.assertRaisesRegex(ValueError,'STALE_REPORT'):patch(self.p,r)

    def test_unsafe_dependency_rejected(self):
        r=scan(self.p);r['findings']=[{'type':'MISSING','target':'main.o','dependency':'../outside.h'}]
        with self.assertRaisesRegex(ValueError,'UNSAFE_PATH'):patch(self.p,r)

    def test_unsupported_configuration_rejected(self):
        (self.p/'Makefile').write_text((self.p/'Makefile').read_text().replace('-O0','-include unknown.h'))
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_FLAGS'):scan(self.p)


class Student241880331E8(unittest.TestCase):
    def test_indirect_include_add_and_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'sample'
            fixture(p)
            baseline = scan(p)

            # 仅修改已有头文件，不增加源文件集合中的文件。
            (p/'config.h').write_text(
                '#include "extra.h"\n#define VALUE 1\n'
            )
            commit(p, 'student E8: add indirect include')
            added = scan(p, baseline)
            full = scan(p)

            self.assertEqual(
                added['actual'],
                {
                    'main.o': ['config.h', 'extra.h', 'main.c'],
                    'helper.o': ['helper.c'],
                },
            )
            self.assertEqual(added['reused'], [])
            self.assertEqual(
                set(added['refreshed']), {'main.o', 'helper.o'}
            )
            self.assertEqual(
                added['added'], [['MISSING', 'main.o', 'extra.h']]
            )
            self.assertEqual(
                {(f['type'], f['target'], f['dependency'])
                 for f in added['findings']},
                {
                    ('MISSING', 'main.o', 'config.h'),
                    ('MISSING', 'main.o', 'extra.h'),
                    ('REDUNDANT', 'main.o', 'unused.h'),
                },
            )
            for key in ['actual', 'declared', 'findings']:
                self.assertEqual(added[key], full[key])

            # 移除间接包含，验证新增 MD 随之消除。
            (p/'config.h').write_text('#define VALUE 1\n')
            commit(p, 'student E8: remove indirect include')
            removed = scan(p, added)
            full_after_remove = scan(p)

            self.assertEqual(removed['actual'], baseline['actual'])
            self.assertEqual(removed['findings'], baseline['findings'])
            self.assertEqual(
                removed['resolved'],
                [['MISSING', 'main.o', 'extra.h']],
            )
            self.assertEqual(removed['added'], [])
            self.assertEqual(removed['reused'], [])
            self.assertEqual(
                set(removed['refreshed']), {'main.o', 'helper.o'}
            )
            for key in ['actual', 'declared', 'findings']:
                self.assertEqual(removed[key], full_after_remove[key])

if __name__=='__main__':unittest.main()
