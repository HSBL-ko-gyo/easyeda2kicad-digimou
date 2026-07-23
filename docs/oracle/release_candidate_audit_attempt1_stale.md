# RC監査結果

## 結論

**Release Candidateとしては却下です。**
設計の大枠は良いものの、現物はそのままではimportできず、さらに部品同一性・検索完全性・キャッシュ証拠性に誤部品を採用し得る欠陥が残っています。

### 実行確認

| 確認               | 結果                                                               |
| ---------------- | ---------------------------------------------------------------- |
| 提供された最新版をそのまま実行  | `sanitize_public_url` が `cache.py` に存在せず、pytest収集時に`ImportError` |
| 監査用コピーに不足関数だけ仮実装 | **102 passed / 15 failed**                                       |
| 15 failuresの原因   | DigiKey/MouserのJSON fixture 2ファイルが提供物に存在しない                      |
| 独自の欠陥再現テスト       | 異メーカー混入、DigiKey/Mouser打切り誤判定、数値MPN受理、raw欠落キャッシュ受理を再現             |
| Legacy/KiCad全回帰  | golden、fixture、未変更upstream一式が不足し再現不能                             |

最新版`service.py`は存在しない`sanitize_public_url`をimportしています。

---

# BLOCKER

## B0 — RCを構成するファイルの版が一致していない

**Affected:**
`easyeda2kicad/metadata/service.py`
`easyeda2kicad/metadata/cache.py`
RC作成処理

最新版`service.py`は`sanitize_public_url`を使用していますが、提供された`cache.py`にはprivateな`_sanitize_url`しかありません。そのためCLI、サービス、テストがimport段階で停止します。

**最小修正:** 同一commitからsdist/wheel/source archiveを作り直し、空の環境へインストールして`python -m easyeda2kicad --help`とpytest収集を実行する。

**Timing:** **FIX NOW。** この状態では他の修正内容以前にRCが成立していません。

---

## B1 — 同じMPNを持つ別メーカー品を同一部品としてマージできる

**Affected:**
`metadata/service.py`
`metadata/merge.py`
`tests/test_metadata_service.py`
`tests/test_metadata_merge.py`

最新版でもDigiKey/Mouserへ渡すメーカー制約はユーザー指定値だけです。CAD/LCSCから判明したメーカーと異なっていても、そのレコードを除外せず「表示名のconflict」として残します。コードとテストはこの挙動を意図的に維持しています。

監査プローブでは、LCSC=`Texas Instruments`、DigiKey=`Analog Devices`、MPN=`SAME-1`を与えると、両方が`distributor_records`に入りました。これはCADと購買情報を別メーカー間で接続する可能性があります。

**最小修正:** CAD/LCSCが確定したメーカーと正規化後に一致しない外部レコードは、購買レコードとシンボルフィールドから除外する。診断には元値を残し、`MANUFACTURER_UNVERIFIED`＋`PARTIAL`とする。alias tableやfuzzy matchは導入しない。

**Timing:** **FIX NOW。**

---

## B2 — DigiKeyの先頭50件だけで一意性を決定している

**Affected:**
`providers/digikey.py`
`tests/test_provider_digikey.py`

`RecordCount=50`、`RecordStartPosition=0`固定で、ページングも公式総件数との照合もありません。51件目以降に別メーカーの同一MPNがあっても一意と判断できます。`ExactMatches`内の不正要素についても検査が不均一です。

監査プローブでは、`ProductsCount=10`で1件しか返していない応答から、その1件が正常な完全一致として選択されました。

**最小修正:** 総件数を必須の非負整数として検証し、全ページを取得する。全件取得を保証できない場合は`NOT_FOUND`や一意一致にせず、`AMBIGUOUS/search-truncated`で閉じる。

**Timing:** **FIX NOW。**

---

## B3 — Mouserの検索結果打切りを完全な結果として扱う

**Affected:**
`providers/mouser.py`
`tests/test_provider_mouser.py`

`NumberOfResult`を読んでいますが、非ゼロなのに`Parts`が空の場合しか拒否しません。10件宣言・1件返却でも、その1件が一意な完全一致になります。`SearchResults`欠落も不正応答ではなく0件扱いです。

監査プローブでも`NumberOfResult=10`、`Parts=1件`から正常選択されました。

**最小修正:** `SearchResults`、`NumberOfResult`、`Parts`を必須にし、ページングしないなら宣言件数と返却件数の完全一致を要求する。不完全なら`AMBIGUOUS/search-truncated`。

**Timing:** **FIX NOW。**

---

## B4 — LCSC metadata providerがCAD endpointを呼んでいる

**Affected:**
`providers/lcsc.py`
`providers/easyeda.py`
`easyeda/easyeda_api.py`
`metadata/service.py`

`LcscProvider.get_part_by_distributor_id()`が最初に`get_cad_data_of_component(part_id)`を呼びます。

このため、

* 明示LCSC IDでCADを二重取得し得る
* `--refresh-metadata`がCAD HTTP通信まで更新する
* LCSC販売情報がCAD payload由来になる
* metadataのraw cacheに公式カタログ応答ではなくCADまたは`{}`が入る

という境界違反になります。

**最小修正:** LCSC ID検索はJLCPCB/LCSCカタログだけで行い、canonical LCSC IDを完全一致検証する。`get_cad_data_of_component`を呼べるのは`EasyedaProvider`だけにする。

**Timing:** **FIX NOW。**

---

## B5 — `normalized.json`がraw証拠なしで信頼される

**Affected:**
`metadata/cache.py`
`metadata/service.py`

cache hit時に読むのは`normalized.json`だけです。`raw_response_cache_key`の文字列が一致しても、対応する`raw.json`の存在、内容、世代は証明されません。

監査プローブでは、`raw.json`が存在しない状態で作成した`normalized.json`がoffline modeで正常に読み出されました。

個別ファイルのatomic writeはありますが、rawとnormalizedの組をtransactionまたはhashで束縛していません。

**最小修正:**

* 両envelopeへ同じgeneration IDと`raw_sha256`を格納
* normalized hit時にrawの存在、provider、request、generation、hashを検証
* 可能ならrawから再normalize・再完全一致選択
* cache schema versionを更新

**Timing:** **FIX NOW。**

---

## B6 — 不正な型のMPNが文字列化され完全一致する

**Affected:**
`providers/base.py`
`providers/digikey.py`
`providers/mouser.py`
`providers/lcsc.py`
`metadata/models.py`

`optional_text()`と`normalize_mpn()`が値を`str()`へ変換します。このため数値`123`、boolean、list、mappingなどが正規のidentity textとして扱われ得ます。

監査プローブでは、DigiKey応答内の数値MPN `123`が文字列`"123"`へ変換され、ユーザー検索`"123"`との完全一致になりました。

**最小修正:** MPN、manufacturer、LCSC ID、distributor part number専用の`identity_text()`を設け、非空の`str`以外を`INVALID_RESPONSE`にする。説明文などだけ従来のlenient変換を使う。

**Timing:** **FIX NOW。**

---

## B7 — manifestが生成済みKiCad libraryを上書きできる

**Affected:**
`__main__.py`
`metadata/manifest.py`
CLI tests

現在のvalidationはJSONとCSVが互いに同じパスでないことしか確認しません。`--manifest-json`を`<output>.kicad_sym`と同じにすると、シンボル生成後にmanifest writerがそれをatomic replaceし、成功終了できます。

**最小修正:** output正規化後、manifestパスが次と衝突する場合に拒否する。

* `<output>.kicad_sym`
* `<output>.pretty`配下
* `<output>.3dshapes`配下
* SVG使用時の`<output>.svgs`配下

Windowsではcase-insensitive比較とdrive差も扱う。

**Timing:** **FIX NOW。**

---

## B8 — Legacy CLIとKiCad出力互換性のrelease evidenceがない

**Affected:**
`tests/test_regression.py`
CI
golden files
Python version matrix

Legacy dispatch自体は分離されています。しかしgolden directoryがなければ比較テストがskipされ、提供物にはそのgoldenと一部provider fixtureがありません。Python 3.9+対応に対して、記録されたbaselineはPython 3.12.13のみです。

今回もDigiKey/Mouser fixture不足により15件が`FileNotFoundError`になり、CLI testsは未変更upstreamファイル不足で完全実行できませんでした。

**最小修正:**

* provider fixtureとoffline CAD fixtureを全て同梱
* golden不在をrelease CIではskipでなくfailureにする
* baseline commitとRCをPython 3.9および現行Pythonで実行
* legacy commandのstdout、stderr、exit code、symbol、footprint、3Dを比較
* KiCad version別symbol出力をbyte単位または構文木単位で比較

**Timing:** **実装修正後、RC宣言前の必須gate。**

---

## B9 — AGPL-3.0の変更通知が不足している

**Affected:**
`README.md`または`NOTICE`
`setup.py`
sdist/wheel/source archive

LICENSEとclassifierがAGPL-3.0のままなのは正しい一方、modified versionであること、変更日、fork URL、baseline commitを示すrelease-facing noticeがありません。`setup.py`もupstream情報だけです。

**最小修正:** top-level noticeへ次を記載する。

* uPesy/easyeda2kicad.pyのmodified version
* baseline `fff10a38619963d7cb1c57d779655a9ea4572e95`
* 変更・release日
* fork source URLとcontributor
* AGPL-3.0継続

**Timing:** **実装修正後、RC packaging前の必須gate。**

---

# SHOULD FIX

## S1 — hidden `Verification Status`が安定プロパティではない

同一CADでも、DigiKey/Mouserの認証失敗やrate limitにより`VERIFIED`と`PARTIAL`が変わり、KiCad symbolのbyte列が変化します。またDigiKey/Mouser part numberの選択が最低MOQ依存なので、販売条件変化でもhidden fieldが変わります。

**Fix:** symbolにはCAD-only verificationだけを格納するか、status自体を除外する。part number選択はMOQ非依存にする。
**Timing:** 次RC前。

## S2 — 認証情報不足が通常出力で見えない

missing credentialは内部の`provider_errors`へ残りますが、`--show-conflicts`またはmanifestなしでは表示されません。symbol-only commandが成功しながら指定providerの情報だけ消えます。

**Fix:** provider、code、operation、HTTP statusだけを安全なwarningとして常時表示する。
**Timing:** 次RC前。

## S3 — offline CAD cache破損がcache missへ化ける

`cache_corrupt`設定後にoffline処理が`offline_cache_miss`で上書きします。

**Fix:** 既存のcorruption状態を保持し、network callなしで`CACHE_CORRUPT`を返す。
**Timing:** 次RC前。

## S4 — 明示datasheet URL検証が未完成

今回の最新版は共有URL validatorを使おうとしていますが、その関数自体がRCに含まれていません。またHTTP(S)確認だけでなく、datasheet URLとprovider product URLが同一でないことも必要です。

**Fix:** 一つのvalidatorでscheme、authority、credentials、product-page equalityを検査し、自動・明示選択の両方に使用する。
**Timing:** B0修正と同時。

## S5 — `--project-relative`のpath処理

relative pathとabsolute CWDへ直接`relative_to()`を使用しており、通常の相対パス、CWD外、Windows別driveで失敗します。legacy pathでは未捕捉例外になり得ます。

**Fix:** 両方resolveしてからproject root内であることを検証し、別driveなどはargument errorにする。
**Timing:** 次RC前。

## S6 — metadata-onlyでもsymbolとfootprintの両方を要求する

`_verify_metadata_cad`がmanifest-only、symbol-only、3D-onlyでも両方をparseし、pin/pad setを要求します。legacy pathなら生成可能なsymbolでもmetadata pathだけ失敗し得ます。

**Fix:** requested artifactだけをparseし、pin/pad照合は両方が必要なactionでのみ必須化する。
**Timing:** 次RC前。

## S7 — U+2212 MINUS SIGNをdash相当として扱わない

現実のコピーMPNに使われるU+2212はUnicode category `Sm`なので、現在の`Pd`変換対象外です。

**Fix:** presentation-equivalentと認める文字だけ明示的translation tableにする。separator削除や位置変更はしない。
**Timing:** RC後でもよいが、正式release前が望ましい。

## S8 — DigiKey client IDがsecret scrub対象外

token、client secret、API keyは対象ですが、`client_id`／`clientId`は対象外です。通常経路で直接漏れる箇所は確認できませんでしたが、「credential valueを保存しない」という仕様とは一致しません。

**Fix:** cache側とprovider側の両scrubberへclient IDとheader名variantを追加する。
**Timing:** 次RC前。

---

# OPTIONAL

**O1 — cache key実装の二重化。** `providers/base.py`と`metadata/cache.py`に別実装があり、テストが実運用経路ではない側だけを検証し得ます。cache側をauthorityに統一し、provider側はcompatibility wrapperへ。

**O2 — modelsの説明が実装と不一致。** docsではimmutableですが、実際はvalidated mutable dataclassです。実装をfreezeするのではなく文書を修正するのが小変更です。

**O3 — LCSC product image scrapingのscope逸脱。** metadata runtimeの直接blockerではありませんが、EasyEDA APIへHTML scraping責務が混入しています。baseline後の追加なら別変更へ分離すべきです。

---

# 問題が見つからなかった／方向性が正しい部分

* 普通の`--lcsc_id`をmetadata mergeへ通さないlegacy dispatchは存在する。
* 通常の文字列MPNではsuffixと`-`、`_`、`/`の位置を保持しており、近似部品への自動置換はしない。
* 明示LCSC ID＋MPNは、外部providerを呼ぶ前に実CAD payloadのidentity evidenceと照合する。
* DigiKey tokenはmemory内、Mouser API keyは安全なprovider exceptionへ変換され、通常経路でsecretをmanifestへ出す設計ではない。
* stock、price、MOQ、currency、retrieval time、cache key、provider errorそのものは直接symbol propertyへ入れていない。
* 最新差分により、以前の「manufacturerをmerge後に変更してconflict/provenanceが不整合になる」問題には補正処理とテストが追加されています。ただし、別メーカーのレコード自体を残すB1は解消していません。

## Release gate

次の順序が最小です。

1. B0を直して単一commit由来の実行可能artifactを作る
2. B1～B7のruntime/data-integrity blockerを修正
3. S1～S6、S8を修正
4. fixture、golden、Python 3.9 matrix、live credential-gated smoke test、secret scanを実行
5. AGPL noticeを含むsdist/wheel/source archiveを再生成
6. その生成済みartifact自体を再監査

**現時点の判定: `NOT READY FOR RC`。**

