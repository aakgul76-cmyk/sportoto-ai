# Spor Toto Analiz — minimum çalışan sürüm

Bu proje API-Football'dan yaklaşan 20 maçı alır, JSON/CSV olarak saklar ve basit bir GitHub Pages ekranında gösterir. Bilgisayarınızın açık kalması gerekmez.

## Kurulum

### 1. GitHub'da boş repository açın

- GitHub'da **New repository** seçin.
- Adını `sportoto-ai` yazın.
- Ücretsiz GitHub Pages için **Public** seçin.
- README eklemeden boş repository oluşturun.

### 2. Bu klasörü GitHub'a yükleyin

GitHub'ın yeni repository sayfasında gösterdiği yükleme adımlarını uygulayın veya dosyaları web arayüzünden yükleyin. `.github` klasörünün de yüklendiğini kontrol edin.

### 3. API anahtarını Secret olarak ekleyin

- Repository'de **Settings → Secrets and variables → Actions** bölümünü açın.
- **New repository secret** seçin.
- Name: `API_FOOTBALL_KEY`
- Secret: API-Football hesabınızdaki anahtarı yapıştırın.

Anahtarı hiçbir kod dosyasına yazmayın.

### 4. GitHub Pages'i açın

- **Settings → Pages** bölümüne gidin.
- **Build and deployment → Source** alanında **GitHub Actions** seçin.

### 5. İlk çalışmayı başlatın

- **Actions → Spor Toto verilerini guncelle** bölümünü açın.
- **Run workflow → Run workflow** seçin.
- İşlem yeşil olduğunda **Settings → Pages** altında site adresi görünür.

Sistem bundan sonra her gün İstanbul saatiyle 08:00 ve 18:00'de çalışır. GitHub yoğunluğuna göre birkaç dakikalık gecikme olabilir.

## Dosya yapısı

```text
sportoto-ai/
├── .github/workflows/update-data.yml  # Zamanlama ve yayınlama
├── scripts/fetch_data.py              # API bağlantısı
├── data/matches.json                  # JSON arşivi
├── data/matches.csv                   # CSV arşivi
├── docs/index.html                    # Web paneli
├── docs/data/matches.json             # Panelin okuduğu veri
└── requirements.txt                   # Python kütüphaneleri
```

## Yerel deneme (isteğe bağlı)

PowerShell'de proje klasöründe:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:API_FOOTBALL_KEY="ANAHTARINIZ"
python scripts/fetch_data.py
```

Bu ilk sürüm tahmin üretmez; önce veri alma, otomatik çalışma ve web yayınının sağlam çalıştığını doğrular. Sonraki aşamada Spor Toto'daki 15 maçı seçme ve 1/X/2 olasılık hesabı eklenebilir.
