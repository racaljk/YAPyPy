import ast
import pytest
from yapypy.extended_python.pybc_emit import py_compile
from yapypy.extended_python.parser import parse
from Redy.Tools.PathLib import Path
from os.path import splitext
from textwrap import dedent
from bytecode import Bytecode
import rbnf.zero as ze
import unittest
ze_exp = ze.compile(
    r"""
[python] import rbnf.std.common.[recover_codes]
Space   := ' '
NL      := R'\n'
Keyword := 'test:' 'prepare:' '>>>' 
NoSwitch ::= ~Keyword
Doctest ::= [(~'prepare:')* 'prepare:' (NoSwitch* '>>>' prepare_lines<<((~NL)+) NL+)*]
            (~'test:')* 'test:' (NoSwitch* '>>>' test_lines<<((~NL)+))* 
            ->
              prepare_lines = recover_codes(sum(prepare_lines, [])) if prepare_lines else ''
              test          = recover_codes(sum(test_lines, []))    if test_lines else ''
              return prepare_lines, test
                
lexer   := R'.'
TestCase ::= [it=Doctest] _* -> it or None
""",
    use='TestCase')

yapypy = Path('yapypy')


def dedent_all(text: str):
    while text.startswith(' ') or text.startswith('\t'):
        text = dedent(text)
    return text


class DocStringsCollector(ast.NodeVisitor):
    def __init__(self):
        self.docs = []

    def _visit_fn(self, node: ast.FunctionDef):
        head, *_ = node.body

        if isinstance(head, ast.Expr):
            value = head.value
            if isinstance(value, ast.Str):
                res = ze_exp.match(value.s).result

                if res:
                    self.docs.append((node.name, node.lineno, *res))
        self.generic_visit(node)

    visit_FunctionDef = _visit_fn


class Test(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def test_all(self):
        for each in filter(lambda p: p[-1].endswith('.py'), yapypy.collect()):
            filename = each.__str__()

            if each.parent().exists():
                pass
            else:
                each.parent().mkdir()

            with each.open('r') as fr:
                collector = DocStringsCollector()
                mod = ast.parse(fr.read())
                collector.visit(mod)

            mod_name, _ = splitext(each.relative())

            for idx, [fn_name, lineno, prepare_code,
                      test_code] in enumerate(collector.docs):

                context = {'self': self}
                prepare_code = dedent_all(prepare_code)
                test_code = dedent_all(test_code)
                try:
                    code = compile(prepare_code, filename, "exec")
                except SyntaxError as exc:
                    exc.lineno = lineno
                    exc.filename = filename
                    raise exc
                bc = Bytecode.from_code(code)
                bc.filename = filename
                bc.first_lineno = lineno
                exec(bc.to_code(), context)

                try:
                    code = py_compile(parse(test_code).result)
                except SyntaxError as exc:
                    exc.lineno = lineno
                    exc.filename = filename
                    raise exc
                bc = Bytecode.from_code(code)
                bc.filename = filename
                bc.first_lineno = lineno
                exec(bc.to_code(), context)

                print(f'{mod_name}.{fn_name} passed test')


if __name__ == '__main__':
    unittest.main()