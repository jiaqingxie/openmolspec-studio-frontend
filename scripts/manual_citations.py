"""Full bibliographic references shared by the project site and manual."""

REFERENCES = {
    'nmrshiftdb': ('Steinbeck, C., Krause, S. & Kuhn, S. NMRShiftDB—Constructing a Free Chemical Information System with Open-Source Components. Journal of Chemical Information and Computer Sciences 43, 1733–1739 (2003). doi:10.1021/ci0341363.', 'https://doi.org/10.1021/ci0341363'),
    'glacier': ('Wang, R.-X., Wang, R. & Coley, C. W. GLACIER: Rethinking Mass Spectrum Prediction as an Object Detection Problem. NeurIPS 2026. arXiv:2606.29161 (2026).', 'https://arxiv.org/abs/2606.29161'),
    'iceberg': ('Wang, R., Manjrekar, M., Mahjour, B., Avila-Pacheco, J., et al. Neural Spectral Prediction for Structure Elucidation with Tandem Mass Spectrometry. bioRxiv (2025). doi:10.1101/2025.05.28.656653.', 'https://doi.org/10.1101/2025.05.28.656653'),
    'magma': ('Ridder, L., van der Hooft, J. J. J. & Verhoeven, S. Automatic Compound Annotation from Mass Spectrometry Data Using MAGMa. Mass Spectrometry 3, S0033 (2014). doi:10.5702/massspectrometry.S0033.', 'https://doi.org/10.5702/massspectrometry.S0033'),
    'openspec': ('OpenMolSpec contributors. openSpec models and benchmark training workflows. Source archive, v1.0 (2026).', 'https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/documentation/assets/benchmarks'),
    'inversions': ('NMRInversions.jl contributors. NMRInversions.jl: inversion of NMR relaxation and diffusion measurements. Software and theory documentation. Accessed 18 November 2026.', 'https://github.com/aris-mav/NMRInversions.jl'),
    'deepseek_harness': ('DeepSeek-AI. DeepSeek Harness: modular agent tools and execution infrastructure. Software repository. Accessed 18 November 2026.', 'https://github.com/deepseek-ai/deepseek-harness'),
    'nmrnet': ('Xu, F., Guo, W., Wang, F., Yao, L., Wang, H., Tang, F., Gao, Z., Zhang, L., E, W., Tian, Z.-Q., et al. Toward a unified benchmark and framework for deep learning-based prediction of nuclear magnetic resonance chemical shifts. Nature Computational Science 5, 292–300 (2025). doi:10.1038/s43588-025-00783-z.', 'https://doi.org/10.1038/s43588-025-00783-z'),
    'opendatalab': ('OpenDataLab. WanJuan MolSpectra, version 1.0.3. Experimental molecular spectroscopy dataset.', 'https://opendatalab.com/'),
    'nmrexp': ('Wang, J.-J., Jin, Y., Zhi, C.-Y., et al. NMRexp: A database of 3.3 million experimental NMR spectra. Scientific Data 12, 1954 (2025). doi:10.1038/s41597-025-06245-5.', 'https://www.nature.com/articles/s41597-025-06245-5'),
    'nmrtrans': ('Yang, L., Yang, Z., Xie, J., Wang, Y., Gao, B., Fu, T., Wei, X., Sun, J., Wu, J., He, C., Li, Y. & Gu, Q. NMRTrans: Structure Elucidation from Experimental NMR Spectra via Set Transformers. arXiv:2602.10158 (2026).', 'https://arxiv.org/abs/2602.10158'),
    'nmrgym': ('Fang, Z., Yang, C., Yu, H., Luo, H., He, H., Xie, J., Yang, Z. & Xia, J. NMRGym: A Comprehensive Benchmark for Nuclear Magnetic Resonance Based Molecular Structure Elucidation. arXiv:2601.15763 (2026).', 'https://arxiv.org/abs/2601.15763'),
    'massspecgym': ('Bushuiev, R., Bushuiev, A., de Jonge, N. F., Young, A., et al. MassSpecGym: A benchmark for the discovery and identification of molecules. Advances in Neural Information Processing Systems 37, Datasets and Benchmarks Track (2024). arXiv:2410.23326.', 'https://arxiv.org/abs/2410.23326'),
    'massbank': ('Horai, H., Arita, M., Kanaya, S., et al. MassBank: a public repository for sharing mass spectral data for life sciences. Journal of Mass Spectrometry 45, 703–714 (2010). doi:10.1002/jms.1777.', 'https://doi.org/10.1002/jms.1777'),
    'qm9s': ('Zou, Z., Zhang, Y., Liang, L., Wei, M., Leng, J., Jiang, J., Luo, Y. & Hu, W. A deep learning model for predicting selected organic molecular spectra. Nature Computational Science 3, 957–964 (2023). doi:10.1038/s43588-023-00550-y.', 'https://www.nature.com/articles/s43588-023-00550-y'),
    'qme14s': ('Yuan, M., Zou, Z. & Hu, W. QMe14S, A Comprehensive and Efficient Spectral Dataset for Small Organic Molecules. arXiv:2501.18876 (2025).', 'https://arxiv.org/abs/2501.18876'),
    'openmolspec': ('OpenMolSpec contributors. OpenMolSpec: Chemical spectroscopy datasets, models and learning workflows. Software release v1.0 (2026).', 'https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/tag/v1.0'),
}


def markdown(keys, en=True):
    """Render complete citations at the bottom of a documentation page."""
    text='\n## '+('References' if en else '参考文献')+'\n\n'
    for key in dict.fromkeys(keys):
        reference,url=REFERENCES[key]
        text+=f'- {reference} [Source]({url})\n'
    return text
