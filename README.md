# without-coffee-rpn — Decaf

**Decaf** は、逆ポーランド記法 (RPN) を採用したスタックベースの汎用プログラミング言語です。
コーヒー抜き (*decaf*) でも読みやすいことを目指しています。

```
: fact ( n -- n! )
  | n |
  n 1 <= [ 1 ] [ n 1 - fact n * ] if ;

"10! = {}" { 10 fact } fmt println     # => 10! = 3628800
```

- スタックベースの実行モデル (データスタック 1 本 + レキシカルスコープの変数)
- ユーザー定義関数 (`: 名前 ... ;`) と再帰 (10 万段以上の深い再帰にも対応)
- 条件分岐 (`if` / `when` / `unless` / `cond`)
- ループ (`while` / `times` / `for` / `for-step` / `each` / `loop` + `break` / `continue`)
- 数値 (任意精度整数・浮動小数点数)、文字列、真偽値、`nil`、リスト、辞書
- クォーテーション (コードブロック) によるクロージャと高階関数 (`map` / `filter` / `reduce` ...)
- ファイルの読み書き、標準入出力、コマンドライン引数
- 例外処理 (`throw` / `try`)、モジュール (`import`)
- `.dcf` ファイルを実行する CLI と対話型 REPL

実装は Python 3.10 以降の標準ライブラリのみで動作し、追加の依存はありません。

## 使い方

```sh
# リポジトリから直接実行
bin/decaf examples/hello.dcf

# またはインストールして `decaf` コマンドとして使う
pip install .
decaf examples/hello.dcf
```

| コマンド | 説明 |
| --- | --- |
| `decaf FILE [ARGS...]` | ファイルを実行する (`ARGS` はプログラムから `args` で取得) |
| `decaf -e 'CODE' [ARGS...]` | コード片を実行する |
| `decaf` | REPL を起動する (標準入力が端末でなければプログラムとして読み込む) |
| `decaf - < prog.dcf` | 標準入力からプログラムを読み込んで実行する |
| `decaf -i FILE` | ファイルを実行した後、その状態のまま REPL に入る |
| `decaf --check FILE` | 構文チェックのみ行う |
| `decaf --words` | 組み込みワードとスタック効果の一覧を表示する |

終了コードは、正常終了で `0`、エラーで `1`、`n exit` で `n` です。
エラー時はファイル名・行・桁とコールスタックを表示します。

```
$ decaf -e ': f 1 "x" + ; f'
<eval>:1:11: error: '+': cannot add int and string (use 'str' to convert to a string first)
  at <eval>:1:11 (in f)
  at <eval>:1:15 (in top level)
```

`#!/usr/bin/env decaf` で始めれば、スクリプトとして直接実行することもできます。

### REPL

```
$ decaf
Decaf 0.1.0 REPL — type 'help' for help, Ctrl-D to quit.
> 3 4 +
  <1> 7
> : sq dup * ;
  <1> 7
> sq .
49
> help swap
swap  ( a b -- b a )
```

各行の実行後にスタックの内容を表示します。エラーが起きた場合はスタックを実行前の状態に戻します。
`[` や `:` を閉じずに改行すると、続きの行を入力できます。

## 言語ガイド

### 実行モデル

プログラムは空白で区切られた **ワード** の列です。左から順に評価され、

- リテラル (数値・文字列など) はスタックに積まれ、
- ワードはスタックから引数を取り出し、結果をスタックに積みます。

```
2 3 + 4 *      # (2 + 3) * 4 = 20
```

スタック効果は `( 入力 -- 出力 )` の形で表記します。`( ... )` はコメントとして扱われるので、
関数定義にそのまま書けます。`#` から行末までもコメントです。

### 値の種類

| 型 | 例 | 備考 |
| --- | --- | --- |
| `int` | `42` `-7` `0xFF` `0b1010` | 任意精度 |
| `float` | `3.14` `1e-3` | |
| `string` | `"hello\n"` | エスケープ: `\n \t \r \0 \e \\ \" \u{3042}` |
| `bool` | `true` `false` | |
| `nil` | `nil` | 値がないことを表す |
| `list` | `{ 1 2 3 }` | 可変長・可変 |
| `dict` | `dict "k" 1 put` | キーは数値・文字列・真偽値・nil |
| `quote` | `[ dup * ]` | 未実行のコードブロック (クロージャ) |
| `function` | `&fact` | 関数への参照 |

真偽判定では `false` `nil` `0` `0.0` `""` 空リスト・空辞書が偽、それ以外が真です。

### リストリテラル

`{ ... }` の中身は **その場で評価** され、積まれた値がリストになります。

```
{ 1 2 + 10 "x" }      # => { 3 10 "x" }
{ }                   # 空リスト
```

### 変数

```
42 -> x              # スタックの値をローカル変数 x に束縛
x x * println        # 変数名を書くと値が積まれる => 1764

1 2 3 | a b c |      # 複数の値をまとめて束縛 (a=1 b=2 c=3)

100 => total         # グローバル変数に代入 (関数の中からでも)
```

- トップレベルで `->` するとグローバル変数になります。
- 関数の中の `->` / `| ... |` はその呼び出し専用のローカル変数です (再帰しても干渉しません)。
- 変数の参照は「ローカル → グローバル → 関数」の順に解決されます。
- 組み込みワードと同じ名前の変数・関数は定義できません。

### 関数

```
: 名前 ( スタック効果 ) 本体 ;
```

```
: square ( x -- x*x ) dup * ;
: hyp ( a b -- c ) | a b | a square b square + sqrt ;

3 4 hyp println       # => 5
```

- 関数定義はファイル内で巻き上げられるので、定義より前で呼び出したり、相互再帰したりできます。
- `return` で関数から抜けます (ループやクォーテーションの中からでも可)。
- `&名前` で関数 (組み込みワードも可) への参照を積み、`call` や高階関数に渡せます。

```
: even? | n | n 0 = [ true ] [ n 1 - odd? ] if ;
: odd?  | n | n 0 = [ false ] [ n 1 - even? ] if ;
{ 1 2 3 } &square map println      # => { 1 4 9 }
```

### クォーテーション

`[ ... ]` は実行されないままスタックに積まれるコードブロックで、`call` で実行します。
定義された場所の変数を参照・更新できるクロージャです。

```
[ 1 + ] -> plus1
5 plus1 call          # => 6

: adder ( n -- quote ) | n | [ n + ] ;
10 adder -> add10
1 add10 call          # => 11
```

### 条件分岐

```
x 0 > [ "positive" ] [ "not positive" ] if      # ( cond [then] [else] -- )
x 0 = [ "zero" println ] when                   # ( cond [then] -- )
x 0 = [ "nonzero" println ] unless              # ( cond [else] -- )

{                                               # ( { [test] [body] ... } -- )
  [ x 0 < ] [ "negative" ]
  [ x 0 = ] [ "zero" ]
  [ true ]  [ "positive" ]
} cond
```

### ループ

```
5 [ "hi" println ] times                 # 5 回繰り返す
1 11 [ println ] for                     # i = 1..10 を積んで本体を実行
10 0 -2 [ println ] for-step             # 10 8 6 4 2
[ n 100 < ] [ n 2 * -> n ] while         # [条件] [本体]
{ "a" "b" } [ println ] each             # リスト・文字列の各要素
dict-value [ | k v | ... ] each          # 辞書はキーと値を積む
{ "a" "b" } [ | x i | ... ] each-index   # 要素と添字
[ ... break ... ] loop                   # break するまで無限ループ
```

`break` で最も内側のループを抜け、`continue` で次の繰り返しに進みます。

### 文字列

```
"Hello" ", " + "World" +       # 連結 => "Hello, World"
"n = " 42 str +                # 数値は str で文字列化してから連結
"x={} y={}" { 1 2 } fmt        # => "x=1 y=2"
"a,b,c" "," split              # => { "a" "b" "c" }
{ "a" "b" } "-" join           # => "a-b"
"hello" 1 3 slice              # => "el"
"42" num   "oops" num          # => 42 nil  (変換に失敗すると nil)
```

### エラー処理

```
[ 10 0 / ] [ "error: " swap + println ] try      # => error: '/': division by zero
[ dict "code" 404 put throw ] [ "code" get println ] try   # 任意の値を throw できる
```

`try` は本体でエラーが起きると、スタックを本体実行前の深さに戻し、エラー値を積んでハンドラを実行します。

### ファイルとモジュール

```
"hello\n" "out.txt" write-file
"world\n" "out.txt" append-file
"out.txt" read-file print
"out.txt" read-lines [ println ] each
"out.txt" file-exists? println
"out.txt" delete-file

"lib/mathlib.dcf" import     # 現在のファイルからの相対パス。同じファイルは 1 度だけ読み込む
```

## 組み込みワード一覧

すべてのワードとスタック効果は `decaf --words` で確認できます。

| 分類 | ワード |
| --- | --- |
| スタック操作 | `dup` `drop` `swap` `over` `rot` `-rot` `nip` `tuck` `2dup` `2drop` `2swap` `pick` `depth` `clear` |
| 算術 | `+` `-` `*` `/` `div` `mod` `%` `**` `neg` `abs` `inc` `dec` `min` `max` `floor` `ceil` `round` `sqrt` `sin` `cos` `tan` `asin` `acos` `atan` `atan2` `exp` `log` `log10` `pi` |
| ビット演算 | `bit-and` `bit-or` `bit-xor` `shl` `shr` |
| 比較・論理 | `=` `!=` `<` `>` `<=` `>=` `and` `or` `not` |
| 制御 | `call` `if` `when` `unless` `cond` `while` `loop` `times` `for` `for-step` `each` `each-index` `break` `continue` `return` `exit` |
| 例外 | `throw` `try` `assert` |
| 高階関数 | `map` `filter` `reduce` `find` `any?` `all?` `sort` `sort-by` |
| リスト・列 | `len` `empty?` `get` `put` `del` `push` `pop` `insert` `first` `last` `rest` `slice` `reverse` `contains?` `index-of` `range` `sum` `copy` `spread` `collect` |
| 辞書 | `dict` `keys` `values` `items` `has?` (`get` `put` `del` `len` も使用可) |
| 文字列 | `str` `repr` `num` `int` `float` `upper` `lower` `trim` `split` `words` `lines` `join` `replace` `starts-with?` `ends-with?` `chars` `ord` `chr` `pad-left` `pad-right` `fmt` |
| 型 | `type` `int?` `float?` `number?` `string?` `bool?` `nil?` `list?` `dict?` `quote?` `function?` `callable?` |
| 入出力 | `print` `println` `.` `nl` `eprintln` `.s` `read-line` `read-all` |
| ファイル | `read-file` `read-lines` `write-file` `append-file` `file-exists?` `dir?` `delete-file` `list-dir` `make-dir` |
| システム | `args` `import` `eval` `getenv` `time` `random` `random-int` `seed` `all-words` |

`put` `push` `pop` `del` `insert` はリスト・辞書をその場で書き換え、操作したコレクションを積み直します
(`dict "a" 1 put "b" 2 put` のように連鎖できます)。

## サンプルプログラム

| ファイル | 内容 |
| --- | --- |
| [`examples/hello.dcf`](examples/hello.dcf) | Hello World と基本 |
| [`examples/fizzbuzz.dcf`](examples/fizzbuzz.dcf) | `cond` と `for` |
| [`examples/recursion.dcf`](examples/recursion.dcf) | 階乗・フィボナッチ (メモ化)・ハノイの塔・アッカーマン関数 |
| [`examples/quicksort.dcf`](examples/quicksort.dcf) | 再帰と高階関数によるクイックソート |
| [`examples/loops.dcf`](examples/loops.dcf) | 各種ループ、`break` / `continue`、`map` / `filter` / `reduce` |
| [`examples/primes.dcf`](examples/primes.dcf) | エラトステネスのふるい (コマンドライン引数で上限指定) |
| [`examples/files.dcf`](examples/files.dcf) | ファイルの読み書き・追記・削除 |
| [`examples/wordcount.dcf`](examples/wordcount.dcf) | ファイルの単語頻度を数えてレポートを書き出す |
| [`examples/errors.dcf`](examples/errors.dcf) | `throw` / `try` |
| [`examples/modules.dcf`](examples/modules.dcf) | `import` と関数参照 |
| [`examples/calc.dcf`](examples/calc.dcf) | Decaf で書いた RPN 電卓 (標準入力から式を読む) |

```sh
bin/decaf examples/primes.dcf 100
bin/decaf examples/wordcount.dcf README.md report.txt
echo "3 4 + 2 *" | bin/decaf examples/calc.dcf
```

## 開発

```sh
python3 -m unittest discover -s tests       # テスト一式
python3 tests/test_examples.py --update     # サンプルの期待出力を更新
```

| ファイル | 役割 |
| --- | --- |
| `decaf/lexer.py` | 字句解析 |
| `decaf/parser.py` | 命令列へのコンパイル (関数定義・ブロック・変数束縛) |
| `decaf/interpreter.py` | スタックマシン本体 |
| `decaf/builtins.py` | 組み込みワード |
| `decaf/values.py` | 値の表現・表示・比較 |
| `decaf/cli.py` | コマンドラインと REPL |
