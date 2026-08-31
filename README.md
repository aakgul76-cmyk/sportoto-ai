# Spor Toto AI

Bu proje haftalık Spor Toto 15 maç listesini alır, GitHub Actions ile veri üretir ve GitHub Pages üzerinde yayınlar.

Ana çalışma mantığı iki parçadır:

1. **Liste/veri üretimi:** Resmî Spor Toto bülteni veya yedek kaynak üzerinden 15 maçlık kupon listesi oluşturulur.
2. **Tahmin ve kupon politikası:** football-data.org geçmiş maç verisinden basit Poisson modeli üretilir, ardından üçlü kullanmayan kupon stratejisi uygulanır.

> Not: Bu proje kesin sonuç tahmini üretmez. Amaç karar disiplinini, kolon verimliliğini ve hafta sonu kalibrasyonunu iyileştirmektir.

## Karar politikası

Yeni ana kural:

```text
1X2 üçlü tercih kullanılmaz.
```

Geçerli tercihler:

```text
1, X, 2, 1X, X2, 12
```

Geniş kupon hedefi:

```text
11 çift + 4 tek = 2.048 kolon
```

Dar kupon hedefi:

```text
7-8 çift + kalan maçlar tek = 128-256 kolon
```

Ayrıntılı karar dosyası: [`docs/DECISION_POLICY.md`](docs/DECISION_POLICY.md)

## Tahmin sitesi / oynanma yüzdesi girişi

`data/consensus.csv` dosyası isteğe bağlıdır. Bu dosyaya Spor Toto, Nesine, Bilyoner, Misli, Hedef15 veya benzer kaynaklardan 1-X-2 yüzdeleri girilebilir.

Bu veriler maç sonucunu kopyalamak için değil; konsensüs, tuzak favori, düşük yüzdeli ters taraf ve kolon dağılımı sinyali için kullanılır.

## Dosya yapısı

```text
sportoto-ai/
├── .github/workflows/update-coupon.yml  # Haftalık Spor Toto listesini yeniler
├── .github/workflows/update-data.yml    # Model verisini ve JSON çıktısını üretir
├── scripts/update_coupon.py             # 15 maçlık kupon listesini oluşturur
├── scripts/fetch_data.py                # Football-data geçmişinden model üretir
├── scripts/apply_decision_policy.py     # Üçlüsüz geniş/dar kupon politikasını uygular
├── scripts/reset_consensus.py           # Yeni haftada konsensüs şablonunu sıfırlar
├── data/coupon.csv                      # Bağlayıcı 15 maç listesi
├── data/predictions.csv                 # Manuel geniş/dar tercih alanı
├── data/consensus.csv                   # Tahmin sitesi / oynanma yüzdesi opsiyonel girişi
├── data/matches.json                    # Ana JSON çıktı
├── docs/index.html                      # GitHub Pages paneli
├── docs/data/matches.json               # Panelin okuduğu JSON
└── requirements.txt
```

## Kurulum

GitHub'da repository secret ekleyin:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Secret adı:

```text
FOOTBALL_DATA_TOKEN
```

Değer: football-data.org API anahtarı.

GitHub Pages için:

```text
Settings → Pages → Build and deployment → Source → GitHub Actions
```

## Yerel deneme

PowerShell'de proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FOOTBALL_DATA_TOKEN="ANAHTARINIZ"
python scripts/update_coupon.py
python scripts/reset_consensus.py
python scripts/fetch_data.py
python scripts/apply_decision_policy.py
```

## Haftalık kalibrasyon

Cuma günü son geniş/dar kuponlar belirlendikten sonra cumartesi, pazar ve pazartesi yeni tahmin üretilmez. Oynanan gerçek kuponlar takip edilir.

Başarı ölçümleri:

- geniş kupon sanal/model başarısı,
- dar kupon gerçek oynanan kupon başarısı,
- tek başarı oranı,
- çift başarı oranı,
- yanlış silinen ihtimaller,
- Türkiye / Avrupa ayrı performans,
- tuzak favori ve daraltma hataları.
