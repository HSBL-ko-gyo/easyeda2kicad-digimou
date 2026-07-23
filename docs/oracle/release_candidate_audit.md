監査結果です。

# Release Candidate re-audit 2 — 最終監査結果

## CANARY CHECK

**判定: CANARY PASS**

権威入力として指定された `release_candidate.diff` を直接計算した結果、SHA-256 は次と完全一致しました。

`cf4527f61101258a14cfff487f987a86111da87e453f06760eadb156066a421b`

さらに、直接添付された現行6ソースは、それぞれ canary 記載のSHA-256と一致し、同じファイルを `release_candidate.diff` から復元した内容ともバイト単位で一致しました。

要求された全canaryを確認しました。canary文書が要求する対象は、cache schema、MPN minus正規化、メーカー検証後の制御フロー、DigiKey/Mouser truncation拒否、LCSC catalogue client分離です。

| Canary                                             | 現行ファイル                         | 結果   |
| -------------------------------------------------- | ------------------------------ | ---- |
| `sanitize_public_url`                              | `metadata/cache.py:620-628`    | PASS |
| `CACHE_SCHEMA_VERSION = 2`                         | `metadata/cache.py:20`         | PASS |
| raw/normalized generation・hash・request・timestamp結合 | `metadata/cache.py:495-551`    | PASS |
| `_MPN_MINUS_EQUIVALENTS`                           | `metadata/models.py:16-24`     | PASS |
| U+2212 `MINUS SIGN`                                | `metadata/models.py:19`        | PASS |
| strict `identity_text`                             | `metadata/models.py:28-36`     | PASS |
| `JlcpcbCatalogueClient`生成                          | `metadata/service.py:145-159`  | PASS |
| `MANUFACTURER_UNVERIFIED`直後の`continue`             | `metadata/service.py:448-456`  | PASS |
| `keyword-search-truncated`                         | `providers/digikey.py:397-405` | PASS |
| `part-search-truncated`                            | `providers/mouser.py:231-253`  | PASS |
| LCSC catalogue/CAD分離                               | `providers/lcsc.py:31,42-45`   | PASS |

特に、未検証メーカーはエラー記録後、`continue` により公開レコードへ追加されません。
DigiKeyおよびMouserの件数不一致も、それぞれ明示的に曖昧結果として拒否されています。 

過去のArchitecture Review、consultation diff、過去監査回答およびそのdispositionは、今回の監査根拠として使用していません。

---

# 総合判定

## **RELEASE BLOCKED**

* RELEASE BLOCKER: **1件**
* SHOULD FIX: **2件**
* ACCEPTABLE RISK: **3件**
* OPTIONAL: **必須項目なし**

今回、新たにexact identity境界のfail-openを確認しました。現RCはリリース承認できません。

---

# RELEASE BLOCKER

## RB-RC2-1 — 一部の解析不能候補を捨てて、残った1件をexactとして採用できる

### 現行ファイル行

* `easyeda2kicad/providers/digikey.py:413-427`
* `easyeda2kicad/providers/mouser.py:255-271`
* `easyeda2kicad/providers/lcsc.py:176-192`

各providerの`normalize_response()`は、APIが返した候補を順に変換し、`_record_from_*()`が`None`を返した候補を単に無視します。その後、**全候補が失敗した場合だけ**`INVALID_RESPONSE`になります。

DigiKeyでは、変換できたレコードだけを追加し、元の`products`が非空かつ結果がゼロのときにしか失敗しません。
MouserとLCSCにも同じ構造があります。 

### 問題

例えばAPI応答が次の2候補を返した場合です。

1. 正常で、要求MPNと一致する候補
2. MPNまたはmanufacturerが欠落し、identityを分類できない候補

現在は2番目を捨て、1番目だけでexact matchを成立させます。

しかし、2番目が別identityなのか、同一identityの別包装なのか、破損応答なのかを判定できません。したがって、完全な候補集合から一意性を証明できていません。

添付された現行moduleをそのまま使った最小再現では、DigiKey、Mouser、LCSCのすべてが「正常1件＋identity欠落1件」を正常なexact結果として受理しました。

これは次の設計目標に直接反します。

* false exact MPNを出さない
* truncationや不完全な候補集合で一意性を主張しない
* malformed identityをfail closedにする

### Mouserの関連fail-open

`providers/mouser.py:231-253`では次の処理があります。

```python
parts = search_results.get("Parts") or []
```

このため、`NumberOfResult = 0`で`Parts`自体が欠落または`None`でも、空リストとして正常化されて`NOT_FOUND`相当になります。現canaryとProvider契約は`Parts`を必須としているため、これは`INVALID_RESPONSE`にすべきです。

### 最小修正

3 provider共通で、APIが返した各候補について以下を行います。

1. 候補がmappingであることを確認する。
2. 必須identityから`DistributorRecord`を作れなければ、候補を捨てず直ちに`InvalidResponseError`を送出する。
3. Mouserでは、`Parts`キーの存在を明示的に要求し、値が必ずlistであることを確認する。
4. 次の回帰テストを追加する。

   * 正常1件＋MPN欠落1件
   * 正常1件＋manufacturer欠落1件
   * 正常1件＋非文字列identity1件
   * Mouserの`NumberOfResult=0`＋`Parts`欠落
   * Mouserの`NumberOfResult=0`＋`Parts=None`
   * LCSC ID検索についても正常＋解析不能候補

「全候補が解析不能」の既存テストだけでは不十分で、**混在応答**を明示的に試験する必要があります。

### 再監査要否

**要。**

exact identityのリリースゲートそのものが変わるため、修正後はprovider実装、関連fixture、service統合、cache再検証を含む再監査が必要です。

ただし、この応答が規定上2回目かつ最終のre-auditであるため、**現RCは不合格として閉じる必要があります**。修正版を監査する場合は、新しいRCとして監査サイクルを開始するか、監査回数規定を明示的に変更する必要があります。

---

# SHOULD FIX

## SF-RC2-1 — manifestがCAD出力の祖先パスの場合、事前衝突検知されない

### 現行ファイル行

`easyeda2kicad/__main__.py:426-464`
特に `:453-457`

現在の検証は次だけを拒否します。

* manifestと選択出力が同一
* manifestが`.pretty`、`.3dshapes`、`.svgs`の内部にある

一方、**manifestがCAD出力の祖先である場合**を拒否しません。

例:

```text
--output ./libs/parts
--manifest-json ./libs
```

検証時には通過しますが、CAD出力によって`./libs`がdirectoryになった後、JSON writerが同じパスへファイルを書けず失敗します。先に生成されたCAD成果物が残るため、preflightの目的である「writer実行前に衝突を拒否する」を満たしません。

### 最小修正

各manifestと各選択出力について、両方向を検査します。

```python
_same_or_descendant(resolved_manifest, resolved_output)
or _same_or_descendant(resolved_output, resolved_manifest)
```

次の祖先ケースをテストします。

* `.kicad_sym`
* `.pretty`
* `.3dshapes`
* `.svgs`

さらに、拒否時にprovider、CAD API、exporter、manifest writerが一度も呼ばれないことを確認します。

### 再監査要否

**単独では不要。**
対象テストと全品質ゲートの再実行で足ります。ただしRB-RC2-1の再監査時には同時確認すべきです。

---

## SF-RC2-2 — Provider契約文書の監査状態が古い

### 現行ファイル行

`docs/PROVIDER_CONTRACT.md:3`

現在も次の記載です。

> Status: implemented; Oracle architecture review pending completion



同じRC内の他文書ではArchitecture Review完了済みとされており、公開文書間で状態が矛盾しています。

### 最小修正

例えば次へ更新します。

```text
Status: implemented; Architecture Review completed and dispositioned;
Release Candidate audit pending resolution.
```

RB-RC2-1修正後は、最終状態に合わせて再度更新します。

### 再監査要否

**不要。** 文書差分確認のみで足ります。

---

# ACCEPTABLE RISK

## AR-RC2-1 — DigiKey/Mouserのcredential付き実API実行が未完了

### 現行証拠

* DigiKey: credential不在のためlive smoke skip
* Mouser: credential不在のためlive smoke skip
* official response shapeのfixture、auth、retry、rate limit、truncation、redaction試験は存在



### 評価

実装構造とfixture試験は監査可能ですが、実アカウント固有の権限、レスポンス差異、quota、価格・在庫フィールドは未検証です。外部配布前の人手確認事項として受容可能ですが、「実APIで動作確認済み」とは表現できません。

### 最小対応

承認済みcredentialを使用し、ログへ値を出さないlive smokeを実施して結果だけを記録する。

### 再監査要否

**不要。** 実行記録と結果確認で足ります。応答schema差異が見つかりsourceを修正する場合のみ再監査対象です。

---

## AR-RC2-2 — native Linuxのprocess-level E2Eが未実施

### 現行証拠

Windowsでは実行済みで、`PureWindowsPath`と`PurePosixPath`によるunit testはありますが、native LinuxのE2Eは実行されていません。

### 評価

path処理は相応に防御されていますが、次はunit testだけでは完全に代替できません。

* 実filesystemのcase sensitivity
* symlinkを含む`resolve()`
* file permission
* temporary-file replacement
* console/locale差
* KiCad側のLinux path解釈

### 最小対応

Linux上で代表的なlegacy、metadata、offline、project-relative、manifestコマンドを実行する。

### 再監査要否

**不要。** source変更がなければ実行証拠の追加のみです。

---

## AR-RC2-3 — inherited reference-output matrixの69テストがskip

### 現行証拠

現行snapshotでは全3 Python環境で次の結果です。

* Python 3.9.25: `666 passed, 71 skipped`
* Python 3.12.13: `666 passed, 71 skipped`
* Python 3.14.3: `666 passed, 71 skipped`

71件の内訳は、upstream reference output不足による69件と、credential-gated live test 2件です。

### 評価

C2040のchecked-in goldenおよび直接baseline比較により、代表的なlegacy compatibilityは補われています。ただしupstreamが本来想定した全reference matrixと等価ではありません。

### 最小対応

可能ならupstreamの正規`tests/reference_outputs/`を取得し、改変せず同じmatrixを実行する。内容を推測して再構築してはなりません。

### 再監査要否

**不要。** 新たな差異が発生した場合のみ必要です。

---

# OPTIONAL

現RCの目的に対して、追加で必須とする項目はありません。

将来の公開配布では、upstreamと同じpackage名・versionをそのまま用いず、local version identifierまたは明確なfork versionと配布URLを設定することが望まれます。ただし、現時点ではNOTICEとAGPL-3.0保持が行われており、今回のexact-MPN機能の正否を左右する項目ではありません。

再監査は不要です。

---

# RESOLVED

## 既存CLIおよびEasyEDA→KiCad互換性

* metadata機能は新optionが指定された場合のみ起動する。
* legacy-only invocationは従来の処理経路へdispatchされる。
* 過去にargparse abbreviationとして成立していた`--d`、`--p`、`--pr`、`--pro`も非表示aliasとして保持されている。
* C2040のsymbol、footprint、SVGについてbaseline/currentのbyte comparisonとoffline goldenがある。
* metadata modeだけLCSC IDをcanonical形式へ強化し、legacy modeは従来の`startswith("C")`挙動を維持する。

**判定: RESOLVED**

ただし、KiCad文字列escapingと危険なCAD由来basename拒否は意図された安全修正であり、特殊文字を含む異常入力については旧版とbyte-identicalではありません。

---

## MPN正規化と類似品拒否

* suffixを削除しない。
* separator位置を保持する。
* ASCII `-`、`_`、`/`を区別する。
* U+2212を含む表示上等価なminusだけをその位置でASCII hyphenへ変換する。
* identity fieldは非空文字列のみ受け入れる。
* DigiKey/Mouserのexact optionを信用せず、返却MPNを再検証する。
* 未検証メーカーはmanifest、BOM、KiCad property、positive provenanceへ入らない。

**判定: 基本設計はRESOLVED。ただし、RB-RC2-1の「解析不能候補の混在」が未解決。**

---

## LCSC ID / MPN不一致

* 明示LCSC IDとCAD payload内のLCSC IDを照合する。
* 明示MPNとCAD payload内MPNを照合する。
* caller入力、検索タイトル、descriptionをidentity fallbackに使用しない。
* payloadに必要なidentityがない場合、要求値を補完せず失敗する。
* 明示的な不一致はblocking errorとなる。

**判定: RESOLVED**

---

## Provider責務とCAD境界

* DigiKey/Mouserはmetadataのみ。
* LCSC metadataは専用`JlcpcbCatalogueClient`から取得する。
* `LcscProvider`はEasyEDA CAD transportを呼ばない。
* EasyEDAが唯一のCAD source。
* `--refresh-metadata`でLCSC catalogueを更新してもCAD cacheを更新しない。

**判定: RESOLVED**

---

## Cache / offline / refresh

* `CACHE_SCHEMA_VERSION = 2`。
* rawはcredential-stripped `redacted_raw`として保存される。
* normalizedとrawは共通のgeneration ID、canonical request、timestamp、raw SHA-256で結合される。
* normalized単体やgeneration不一致を信用しない。
* onlineでは24時間freshnessを適用する。
* offlineではstaleな正常pairを許容するが、networkへfallbackしない。
* missing pairは`OFFLINE_CACHE_MISS`、片側欠損・破損は`CACHE_CORRUPT`。
* `--refresh-metadata`はmetadata readだけをbypassする。
* `--offline`との同時指定は拒否する。

**判定: RESOLVED**

---

## 秘密情報

* DigiKey client ID/secret、OAuth token、Mouser API keyはenvironmentから遅延取得される。
* access tokenはmemory内のみ。
* cache key、manifest、KiCad property、provider diagnosticへcredential値を入れない。
* URL userinfo、fragment、secret query parameterを除去する。
* Mouserのkey入りURLやraw exception messageを診断へ保存しない。
* secret-name suffixとcamelCase variantも除去する。
* malformed public URLは公開sinkから除外される。

**判定: RESOLVED**

---

## KiCad propertyおよびvolatile sales data

* metadata propertyはhidden custom propertyとして追加される。
* `Reference`と`Value`の表示挙動は維持される。
* KiCadへ入るのはメーカー、MPN、販売店品番・公開URL、package、lifecycle、CAD source、CAD verification statusなどの安定情報。
* stock、price、price breaks、MOQ、currency、retrieved time、cache key、provider error/diagnosticはKiCadへ入らない。
* metadata modeでは予約名やsales/cache fieldの`--custom-field`上書きを拒否する。
* legacy modeの従来custom-field挙動は維持される。
* `Verification Status`はdistributor availabilityではなくCAD状態だけを表す。

**判定: RESOLVED**

---

## `CAD_NOT_FOUND` / `--require-cad`

* 明示的で矛盾しないEasyEDA `success:false`のみが`CAD_NOT_FOUND`を確定する。
* network errorやinvalid responseをCAD不存在へ変換しない。
* 通常の`CAD_NOT_FOUND`はmetadata-only成功としてexit 0。
* `--require-cad`ではmanifestを書いた後にexit 1。
* corrupt/offline cache、identity未解決、export failure、pin/pad mismatchはblocking。

**判定: RESOLVED**

---

## Windows/Linux path処理

* project-relative pathはcurrent project rootへの包含を確認する。
* Windows cross-driveやout-of-treeを拒否する。
* CAD由来basenameはseparator、control character、Windows device name、末尾dot/spaceを拒否する。
* JSON/CSV同士の同一・祖先子孫関係を拒否する。
* manifestが選択CAD directory内にある場合を拒否する。

**判定: 概ねRESOLVED。ただし、SF-RC2-1の逆方向の祖先衝突が未解決。**

---

## テスト、文書、ライセンス、侵襲性

* Python 3.9/3.12/3.14で同一のfull-suite結果。
* Ruff format、Ruff lint、Python 3.9 strict mypyが通過。
* legacy offline golden、provider fixture、cache corruption、offline、exact mismatch、manifest、custom property、CAD status試験が存在。
* AGPL-3.0を維持。
* `LICENSE`と変更内容を記録した`NOTICE`をpackageへ含める。
* 新規runtime dependencyを追加せず、標準library HTTP clientを使用。
* upstream importer/exporterを置き換えず、metadata orchestrationを追加する構造。
* legacy pathへ及ぶ変更は、文字列escaping、offline support、危険basename拒否など限定された安全修正。

**判定: コード侵襲性およびライセンス面はRESOLVED。Provider契約文書のstatusだけSF-RC2-2。**

---

# 最終結論

**CANARY PASS / RELEASE BLOCKED**

権威入力は正しく取得でき、現行RCを監査できました。過去snapshotの指摘を再掲したものではありません。

今回の不合格理由は、新たに確認した **RB-RC2-1: 混在する解析不能provider候補を捨ててexact uniquenessを成立させられること**です。これはfalse exact MPN防止という本変更の中核要件に直接関わるため、release blockerです。

現RCはリリース不可です。規定上の最終re-auditとして、本監査サイクルの結論は不合格で確定します。

以上を最終判定とします。
