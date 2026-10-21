# Local image-import OCR assets

The account import reads images in the browser. These files are served by LotNeeti so the
browser does not fetch OCR code or language data from a third-party CDN.

- `worker.min.js`: `tesseract.js` 7.0.0, Apache-2.0 (license alongside).
- `tesseract-core-lstm.wasm.js` and `.wasm`: `tesseract.js-core` version locked by `package-lock.json`, Apache-2.0 (license alongside).
- `eng.traineddata.gz`: English `@tesseract.js-data/eng/4.0.0_best_int` from jsDelivr, based on the Tesseract English trained data.

When updating Tesseract, replace the worker and core together and test an image import in
Safari and Chrome. The image itself is not uploaded; only user-reviewed extracted text is
sent to the existing encrypted import preview.
