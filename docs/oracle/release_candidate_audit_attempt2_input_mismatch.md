# Release Candidate re-audit 1 — 入力照合結果

**判定：監査対象スナップショット不一致。RC判定は保留します。**

今回の会話で参照できるファイルは、`attachments-bundle.txt` と `attachments-bundle(1).txt` の2点だけです。`release_candidate_audit_attempt1_stale.md` と `release_candidate_audit_attempt1_disposition.md` 本体は含まれていません。 

さらに、`attachments-bundle(1).txt` には、誤認原因となった過去の `docs/oracle/architecture_review.md` がそのまま保存されています。これは現行判定資料から除外します。

一方、実装側の `attachments-bundle.txt` も、修正後RCではなく古いスナップショットと判断できます。例えば、閉じた指摘に対応するはずの箇所が、固定50件・開始位置0のDigiKey検索のままです。 また、MPN正規化も依然としてUnicodeカテゴリ`Pd`だけを変換しています。

これは **B0–B9／S1–S8を再オープンする判断ではありません**。添付コードが、Codexの現行照合対象だった修正後ツリーと一致していないことを示すものです。

したがって今回の扱いは以下です。

* `release_candidate_audit_attempt1_stale.md`：監査証拠から完全除外
* 埋め込みのArchitecture Review／consultation diff：履歴資料のみ
* B0–B9／S1–S8：修正済みとして持ち越し禁止
* 現在の添付コード：現行RCとして監査しない
* **新規BLOCKER／SHOULD FIX／OPTIONAL：未判定**
* **RC READY／NOT READY：未判定**

正式なre-audit 1には、修正後の現行treeまたは`fff10a3…HEAD`差分、`release_candidate_audit_attempt1_disposition.md`、そのHEADに対するテスト結果が必要です。そこからは過去レビュー文を探索対象にせず、現行コードから独立に再発と新規問題だけを抽出します。
