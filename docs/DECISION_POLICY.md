# Spor Toto Karar Politikası

Bu dosya, kupon üretirken kullanılacak ana kuralları özetler. Amaç 15 maçı körlemesine kapatmak değil, gerçek oynanabilir kupondan gelir üretme ihtimalini artırmak ve analiz başarısını tek/doğru çift tercihleriyle ölçmektir.

## 1. Birincil ürün dar kupondur

Bundan sonra ana değerlendirme sırası şöyledir:

1. **Dar kupon:** Gerçek parayla oynanan ana kupon. Haftalık performansın birincil ölçüsüdür.
2. **Geniş kupon:** Sanal takip ve kalibrasyon kuponu. Dar kuponun üzerine ek ihtimaller taşıyan kontrol aracıdır.

Geniş kupon 15 bilse bile doğrudan gelir üretmez. Bu yüzden başarı raporunda önce dar kuponun sonucu, sonra geniş kuponun neyi önceden radarına aldığı değerlendirilir.

## 2. Üçlü tercih yok

`1X2` artık kullanılmaz.

Geçerli tercihler:

- `1`
- `X`
- `2`
- `1X`
- `X2`
- `12`

Sebep: `1X2` maç sonucunu otomatik kapsar; bu nedenle analiz başarısı sayılmaz ve kolon verimliliğini düşürür.

## 3. Dar kupon hedefi

Ana hedef:

```text
7-8 çift + kalan maçlar tek = 128-256 kolon
```

Dar kupon geniş kuponun basit kısaltması değildir. Önce gerçek oynanacak dar kupon oluşturulur; risk bütçesi, tek/çift seçimi ve sürpriz dağılımı bu kupon için optimize edilir.

## 4. Geniş kupon hedefi

Geniş kupon dar kuponun üzerine kurulan sanal kontrol kuponudur.

Ana hedef:

```text
Dar kupon + ek ihtimaller → 11 çift + 4 tek = 2.048 kolon
```

Geniş kuponun görevi gelir üretmek değil, dar kuponda alamadığımız ama analizde radarımıza giren ihtimalleri takip etmektir. Hafta sonu değerlendirmesinde şu ayrım yapılır:

| Durum | Anlamı |
|---|---|
| Dar kaçırdı, geniş yakaladı | Daraltma / risk bütçesi hatası |
| Dar kaçırdı, geniş de kaçırdı | Analiz/model hatası |
| Dar yakaladı, geniş de yakaladı | Doğru ana karar |
| Dar yakaladı, geniş kaçırdı | Geniş sanal dağılım hatası |

## 5. Türkiye ligi erken sezon kuralı

Ağustos ve eylül döneminde Türkiye maçlarında şu kural uygulanır:

```text
Büyük takım dışı favori %50-58 bandındaysa tek geçilmez.
```

Büyük takım listesi:

- Galatasaray
- Fenerbahçe
- Beşiktaş
- Trabzonspor

Bu kural, ilk haftalardaki yeni kadro uyumu, transfer etkisi, teknik direktör değişimi, reaksiyon maçları ve deplasman sürprizi riskini yükseltmek için kullanılır.

## 6. Tahmin sitesi ve oynanma yüzdesi kullanımı

Tahmin siteleri, Hedef15, Spor Toto yüzdeleri, Nesine, Bilyoner ve Misli dağılımları maç sonucunu kopyalamak için kullanılmaz.

Bu veriler şu amaçlarla kullanılır:

- konsensüs sinyali,
- tuzak favori alarmı,
- düşük yüzdeli ama mantıklı ters tarafı yaşatma,
- kolon dağılımı denetimi.

Bu bilgiler `data/consensus.csv` dosyasına girilebilir. Dosya boş kalırsa algoritma yalnızca model ve manuel tercihleri kullanır.

## 7. Her maç için zorunlu karar soruları

Her maçta şu sorular cevaplanmalıdır:

1. Bu maç dar kuponda tek geçilebilir mi?
2. Tek geçilmezse dar kupon için doğru çift hangisi?
3. Düşük yüzdeli ama yaşatılması gereken taraf var mı?
4. Favori neden puan kaybeder?
5. Geniş sanal kuponda dar kupona hangi ek ihtimal eklenmeli?

## 8. Haftalık çalışma döngüsü

- Salı, çarşamba, perşembe ve cuma: yeni haftanın kuponu analiz edilir.
- Cuma: önce gerçek dar kupon, sonra sanal geniş kupon kesinleştirilir.
- Cumartesi, pazar ve pazartesi: yeni tahmin üretilmez; cuma günü oynanan dar kupon ve sanal geniş kupon takip edilir.
- Salı: yeni kupon haftası başlar.

## 9. Kalibrasyon ölçümü

Hafta sonunda başarı şu sırayla ölçülür:

1. Dar kupon gerçek başarı oranı.
2. Dar kupondaki tek başarı oranı.
3. Dar kupondaki çift başarı oranı.
4. Dar kuponun yanlış sildiği ihtimaller.
5. Geniş sanal kuponun yakaladığı ama dara taşınmayan ihtimaller.
6. Türkiye / Avrupa ayrı performans.
7. Tuzak favori başarı/hata tablosu.
8. Kolon verimliliği.

Sonradan yapılan tahmin revizyonları başarı hesabına katılmaz. Cuma günü oynanan dar kupon gerçek referans, geniş kupon sanal/model referansı olarak ayrı değerlendirilir.
