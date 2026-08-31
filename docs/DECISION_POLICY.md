# Spor Toto Karar Politikası

Bu dosya, kupon üretirken kullanılacak ana kuralları özetler. Amaç 15 maçı körlemesine kapatmak değil, gerçek analiz başarısını tek ve doğru çift tercihleriyle ölçmektir.

## 1. Üçlü tercih yok

`1X2` artık kullanılmaz.

Geçerli tercihler:

- `1`
- `X`
- `2`
- `1X`
- `X2`
- `12`

Sebep: `1X2` maç sonucunu otomatik kapsar; bu nedenle analiz başarısı sayılmaz ve kolon verimliliğini düşürür.

## 2. Geniş kupon hedefi

Ana hedef:

```text
11 çift + 4 tek = 2.048 kolon
```

Bu yapı 2.500 kolon sınırının altında kalır ve üçlü kullanmadan maksimuma yakın kapsama sağlar.

## 3. Dar kupon hedefi

Ana hedef:

```text
7-8 çift + kalan maçlar tek = 128-256 kolon
```

Dar kupon, geniş kuponun basit kısaltması değildir. Ayrı risk dağıtımıdır.

## 4. Türkiye ligi erken sezon kuralı

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

## 5. Tahmin sitesi ve oynanma yüzdesi kullanımı

Tahmin siteleri, Hedef15, Spor Toto yüzdeleri, Nesine, Bilyoner ve Misli dağılımları maç sonucunu kopyalamak için kullanılmaz.

Bu veriler şu amaçlarla kullanılır:

- konsensüs sinyali,
- tuzak favori alarmı,
- düşük yüzdeli ama mantıklı ters tarafı yaşatma,
- kolon dağılımı denetimi.

Bu bilgiler `data/consensus.csv` dosyasına girilebilir. Dosya boş kalırsa algoritma yalnızca model ve manuel tercihleri kullanır.

## 6. Her maç için zorunlu karar soruları

Her maçta şu sorular cevaplanmalıdır:

1. Bu maç tek geçilebilir mi?
2. Tek geçilmezse doğru çift hangisi?
3. Düşük yüzdeli ama yaşatılması gereken taraf var mı?
4. Favori neden puan kaybeder?
5. Dar kupona hangi risk senaryosuyla taşınmalı?

## 7. Kalibrasyon ölçümü

Hafta sonunda başarı şu kırılımla ölçülür:

- tek başarı oranı,
- çift başarı oranı,
- yanlış silinen ihtimaller,
- Türkiye / Avrupa ayrı performans,
- tuzak favori başarı/hata tablosu,
- dar kupona aktarım hataları,
- kolon verimliliği.

Sonradan yapılan tahmin revizyonları başarı hesabına katılmaz. Cuma günü oynanan geniş kupon sanal/model referansı, dar kupon gerçek oynanan kupon olarak ayrı değerlendirilir.
